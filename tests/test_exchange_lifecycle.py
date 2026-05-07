from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from app.exchange.fills import parse_exchange_fill
from app.persistence.database import SessionFactory, create_session_factory, init_db, session_scope
from app.persistence.models import OrderLifecycleState, OrderModel, PositionModel, RiskEventModel
from app.persistence.repositories import ExchangeFillRepository, OrderRepository
from app.workers.exchange_lifecycle import ExchangeLifecycleReconciliationWorker
from trading_bot.core.types import Position, SignalSide
from trading_bot.execution.base import ExchangeOrderStatus, OrderResult
from trading_bot.utils.alerts import AlertQueue


class FakeExecutionClient:
    def __init__(
        self,
        *,
        order_statuses: dict[str, ExchangeOrderStatus] | None = None,
        open_position: Position | None = None,
        open_orders: list[dict[str, object]] | None = None,
        cancel_result: OrderResult | None = None,
    ) -> None:
        self.order_statuses = order_statuses or {}
        self.open_position = open_position
        self.open_orders = open_orders or []
        self.cancel_result = cancel_result or OrderResult(success=True, order_id="cancelled", message="CANCELED")
        self.cancelled_order_ids: list[str] = []

    def get_order_status(self, symbol: str, order_id: str) -> ExchangeOrderStatus | None:
        return self.order_statuses.get(order_id)

    def get_open_position(self, symbol: str) -> Position | None:
        return self.open_position

    def get_open_orders(self, symbol: str) -> list[dict[str, object]]:
        return self.open_orders

    def cancel_order(self, symbol: str, order_id: str) -> OrderResult:
        self.cancelled_order_ids.append(order_id)
        return OrderResult(
            success=self.cancel_result.success,
            order_id=order_id,
            message=self.cancel_result.message,
        )


def _session_factory() -> SessionFactory:
    factory = create_session_factory("sqlite:///:memory:")
    init_db(factory)
    return factory


def _alert_queue(sent: list[str]) -> AlertQueue:
    def sender(text: str, bot_token: str, chat_id: str) -> bool:
        sent.append(text)
        return True

    return AlertQueue(sender=sender, autostart=True)


def _create_order(factory: SessionFactory) -> int:
    with session_scope(factory) as session:
        order = OrderRepository(session).create_pending(
            symbol="ZECUSDT",
            side="BUY",
            quantity=1.0,
        )
        order.exchange_order_id = "order-1"
        return order.id


def _add_exchange_fill(factory: SessionFactory) -> None:
    with session_scope(factory) as session:
        ExchangeFillRepository(session).create_from_fill(
            parse_exchange_fill(
                {
                    "symbol": "ZECUSDT",
                    "id": 1001,
                    "orderId": "order-1",
                    "side": "BUY",
                    "price": "100.0",
                    "qty": "0.25",
                    "quoteQty": "25.0",
                    "realizedPnl": "0",
                    "commission": "0.01",
                    "commissionAsset": "USDT",
                    "buyer": True,
                    "maker": False,
                    "time": 1767225600000,
                },
                fallback_symbol="ZECUSDT",
            )
        )


def test_lifecycle_reconciliation_polls_order_status_and_aggregates_partial_fill() -> None:
    factory = _session_factory()
    order_id = _create_order(factory)
    _add_exchange_fill(factory)
    sent: list[str] = []
    queue = _alert_queue(sent)
    client = FakeExecutionClient(
        order_statuses={
            "order-1": ExchangeOrderStatus(
                order_id="order-1",
                symbol="ZECUSDT",
                status="PARTIALLY_FILLED",
                original_quantity=1.0,
                executed_quantity=0.2,
                avg_price=99.0,
                raw_response={"status": "PARTIALLY_FILLED"},
            )
        }
    )
    worker = ExchangeLifecycleReconciliationWorker(session_factory=factory, client=client, alert_queue=queue)

    summary = worker.reconcile_once(symbols=["ZECUSDT"], cancel_stale_reduce_only=False)

    queue.stop(drain=True)
    with session_scope(factory) as session:
        order = session.get(OrderModel, order_id)

    assert summary.orders_polled == 1
    assert summary.orders_updated == 1
    assert order is not None
    assert order.exchange_status == "PARTIALLY_FILLED"
    assert order.filled_quantity == 0.25
    assert order.remaining_quantity == 0.75
    assert order.avg_price == 100.0
    assert order.state == OrderLifecycleState.ENTRY_PLACED


def test_lifecycle_reconciliation_creates_position_and_alerts_on_external_position_drift() -> None:
    factory = _session_factory()
    sent: list[str] = []
    queue = _alert_queue(sent)
    client = FakeExecutionClient(
        open_position=Position(
            symbol="ZECUSDT",
            side=SignalSide.LONG,
            quantity=0.5,
            entry_price=100.0,
            unrealized_pnl=1.0,
            leverage=5,
        )
    )
    worker = ExchangeLifecycleReconciliationWorker(session_factory=factory, client=client, alert_queue=queue)

    summary = worker.reconcile_once(symbols=["ZECUSDT"])

    queue.stop(drain=True)
    with session_scope(factory) as session:
        position = session.scalar(select(PositionModel))
        event = session.scalar(select(RiskEventModel))

    assert summary.positions_synced == 1
    assert summary.drift_events == 1
    assert position is not None
    assert position.status == "open"
    assert position.quantity == 0.5
    assert event is not None
    assert event.event_type == "position_drift_detected"
    assert event.severity == "CRITICAL"
    assert event.payload["drift_type"] == "exchange_position_without_local_record"
    assert any("[CRITICAL] Position drift detected" in message for message in sent)


def test_lifecycle_reconciliation_closes_local_position_and_cancels_stale_reduce_only_orders() -> None:
    factory = _session_factory()
    with session_scope(factory) as session:
        session.add(
            PositionModel(
                symbol="ZECUSDT",
                side="BUY",
                quantity=0.5,
                entry_price=100.0,
                unrealized_pnl=0.0,
                leverage=5,
                status="open",
                opened_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )
        )
    sent: list[str] = []
    queue = _alert_queue(sent)
    client = FakeExecutionClient(
        open_position=None,
        open_orders=[
            {"orderId": "tp-1", "type": "LIMIT", "side": "SELL", "reduceOnly": True},
            {"orderId": "sl-1", "type": "STOP_MARKET", "side": "SELL", "reduceOnly": "true"},
        ],
    )
    worker = ExchangeLifecycleReconciliationWorker(session_factory=factory, client=client, alert_queue=queue)

    summary = worker.reconcile_once(symbols=["ZECUSDT"])

    queue.stop(drain=True)
    with session_scope(factory) as session:
        position = session.scalar(select(PositionModel))
        events = session.scalars(select(RiskEventModel)).all()

    assert summary.drift_events == 1
    assert summary.stale_orders_cancelled == 2
    assert client.cancelled_order_ids == ["tp-1", "sl-1"]
    assert position is not None
    assert position.status == "closed"
    assert {event.event_type for event in events} == {
        "position_drift_detected",
        "stale_reduce_only_order_cancelled",
    }
