from __future__ import annotations

from sqlalchemy import select

from app.persistence.database import SessionFactory, create_session_factory, init_db, session_scope
from app.persistence.models import OrderLifecycleState, OrderModel, RiskEventModel
from app.persistence.repositories import OrderRepository
from app.workers.failed_unprotected_recovery import FailedUnprotectedRecoveryWorker
from trading_bot.core.types import SignalSide
from trading_bot.execution.base import OrderResult
from trading_bot.utils.alerts import AlertQueue


class FakeExecutionClient:
    def __init__(
        self,
        open_orders: list[dict[str, object]],
        close_result: OrderResult | None = None,
    ) -> None:
        self.open_orders = open_orders
        self.close_result = close_result or OrderResult(success=True, order_id="close-1")
        self.open_order_calls = 0
        self.close_calls = 0

    def get_open_orders(self, symbol: str) -> list[dict[str, object]]:
        self.open_order_calls += 1
        return self.open_orders

    def emergency_close_position(self, symbol: str, side: SignalSide, quantity: float) -> OrderResult:
        self.close_calls += 1
        return self.close_result


def _session_factory() -> SessionFactory:
    factory = create_session_factory("sqlite:///:memory:")
    init_db(factory)
    return factory


def _alert_queue(sent: list[str]) -> AlertQueue:
    def sender(text: str, bot_token: str, chat_id: str) -> bool:
        sent.append(text)
        return True

    return AlertQueue(sender=sender, autostart=True)


def _create_failed_order(factory: SessionFactory, *, quantity: float | None = 0.5) -> int:
    with session_scope(factory) as session:
        order = OrderRepository(session).create_pending(
            symbol="ZECUSDT",
            side="BUY",
            quantity=quantity,
            order_type="MARKET",
        )
        order.exchange_order_id = "entry-1"
        order.avg_price = 100.0
        order.stop_order_id = "sl-1"
        order.take_profit_order_id = "tp-1"
        order.state = OrderLifecycleState.FAILED_UNPROTECTED
        order.requires_manual_review = True
        order.protected = False
        return order.id


def _protected_orders() -> list[dict[str, object]]:
    return [
        {"orderId": "tp-1", "type": "LIMIT", "side": "SELL", "reduceOnly": True},
        {"orderId": "sl-1", "type": "STOP_MARKET", "side": "SELL", "reduceOnly": True},
    ]


def test_failed_unprotected_recovery_marks_order_protected_when_orders_exist() -> None:
    factory = _session_factory()
    order_id = _create_failed_order(factory)
    sent: list[str] = []
    queue = _alert_queue(sent)
    client = FakeExecutionClient(_protected_orders())
    worker = FailedUnprotectedRecoveryWorker(
        session_factory=factory,
        client=client,
        alert_queue=queue,
        max_attempts=1,
        backoff_seconds=0,
    )

    summary = worker.recover_once()

    queue.stop(drain=True)
    with session_scope(factory) as session:
        order = session.get(OrderModel, order_id)
        events = session.scalars(select(RiskEventModel)).all()

    assert summary.scanned == 1
    assert summary.recovered == 1
    assert summary.emergency_closed == 0
    assert client.close_calls == 0
    assert order is not None
    assert order.state == OrderLifecycleState.PROTECTED
    assert order.requires_manual_review is False
    assert events[0].event_type == "failed_unprotected_recovery_reconciliation_attempt"
    assert any("[INFO] Order protection verified" in message for message in sent)


def test_failed_unprotected_recovery_emergency_closes_when_protection_missing() -> None:
    factory = _session_factory()
    order_id = _create_failed_order(factory)
    sent: list[str] = []
    queue = _alert_queue(sent)
    client = FakeExecutionClient([], close_result=OrderResult(success=True, order_id="close-99"))
    worker = FailedUnprotectedRecoveryWorker(
        session_factory=factory,
        client=client,
        alert_queue=queue,
        max_attempts=1,
        backoff_seconds=0,
    )

    summary = worker.recover_once()

    queue.stop(drain=True)
    with session_scope(factory) as session:
        order = session.get(OrderModel, order_id)
        event_types = [event.event_type for event in session.scalars(select(RiskEventModel)).all()]

    assert summary.scanned == 1
    assert summary.recovered == 0
    assert summary.emergency_closed == 1
    assert client.close_calls == 1
    assert order is not None
    assert order.state == OrderLifecycleState.FAILED_UNPROTECTED
    assert order.requires_manual_review is True
    assert order.emergency_close_order_id == "close-99"
    assert "failed_unprotected_recovery_manual_review_required" in event_types
    assert "failed_unprotected_recovery_emergency_close" in event_types
    assert any("[EMERGENCY] Emergency market close submitted" in message for message in sent)


def test_failed_unprotected_recovery_requires_manual_review_for_missing_quantity() -> None:
    factory = _session_factory()
    _create_failed_order(factory, quantity=None)
    sent: list[str] = []
    queue = _alert_queue(sent)
    client = FakeExecutionClient([])
    worker = FailedUnprotectedRecoveryWorker(
        session_factory=factory,
        client=client,
        alert_queue=queue,
        max_attempts=1,
        backoff_seconds=0,
    )

    summary = worker.recover_once()

    queue.stop(drain=True)
    with session_scope(factory) as session:
        event = session.scalar(select(RiskEventModel))

    assert summary.scanned == 1
    assert summary.manual_review == 1
    assert client.open_order_calls == 0
    assert client.close_calls == 0
    assert event is not None
    assert event.event_type == "failed_unprotected_recovery_manual_review"
    assert event.severity == "EMERGENCY"
