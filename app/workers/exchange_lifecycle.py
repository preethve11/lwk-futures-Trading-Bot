"""Exchange lifecycle reconciliation for orders, fills, and position drift."""

from __future__ import annotations

from dataclasses import dataclass, field
import logging

from app.persistence.database import SessionFactory, session_scope
from app.persistence.models import OrderLifecycleState, OrderModel, PositionModel
from app.persistence.repositories import (
    ExchangeFillRepository,
    OrderRepository,
    PositionRepository,
    RiskEventRepository,
)
from trading_bot.core.types import Position
from trading_bot.execution.base import ExchangeOrderStatus, ExecutionClient
from trading_bot.utils.alerts import AlertQueue, AlertSeverity

logger = logging.getLogger("trading_bot.exchange_lifecycle")


@dataclass(frozen=True)
class OrderLifecycleSnapshot:
    """Order fields needed to poll exchange lifecycle outside a DB session."""

    id: int
    bot_session_id: int | None
    symbol: str
    exchange_order_id: str
    state: OrderLifecycleState
    protected: bool

    @classmethod
    def from_model(cls, model: OrderModel) -> OrderLifecycleSnapshot:
        if model.exchange_order_id is None:
            raise ValueError(f"Order {model.id} has no exchange_order_id")
        return cls(
            id=model.id,
            bot_session_id=model.bot_session_id,
            symbol=model.symbol,
            exchange_order_id=model.exchange_order_id,
            state=model.state,
            protected=model.protected,
        )


@dataclass(frozen=True)
class PositionSnapshot:
    """Persisted local position fields needed for drift checks."""

    id: int
    bot_session_id: int | None
    symbol: str
    side: str
    quantity: float
    entry_price: float

    @classmethod
    def from_model(cls, model: PositionModel) -> PositionSnapshot:
        return cls(
            id=model.id,
            bot_session_id=model.bot_session_id,
            symbol=model.symbol,
            side=model.side,
            quantity=model.quantity,
            entry_price=model.entry_price,
        )


@dataclass(frozen=True)
class ExchangeLifecycleSummary:
    """Summary of one lifecycle reconciliation sweep."""

    orders_polled: int = 0
    orders_updated: int = 0
    missing_order_statuses: int = 0
    terminal_order_events: int = 0
    positions_synced: int = 0
    drift_events: int = 0
    stale_orders_cancelled: int = 0
    cancel_failures: int = 0
    errors: list[str] = field(default_factory=list)


class ExchangeLifecycleReconciliationWorker:
    """Poll exchange order statuses, aggregate fills, sync positions, and detect drift."""

    def __init__(
        self,
        *,
        session_factory: SessionFactory,
        client: ExecutionClient,
        alert_queue: AlertQueue,
        quantity_tolerance: float = 1e-9,
    ) -> None:
        self.session_factory = session_factory
        self.client = client
        self.alert_queue = alert_queue
        self.quantity_tolerance = quantity_tolerance

    def reconcile_once(
        self,
        *,
        symbols: list[str] | None = None,
        order_limit: int = 100,
        bot_session_id: int | None = None,
        cancel_stale_reduce_only: bool = True,
    ) -> ExchangeLifecycleSummary:
        order_snapshots = self._load_order_snapshots(limit=order_limit)
        symbols_to_sync = set(symbols or [])
        symbols_to_sync.update(snapshot.symbol for snapshot in order_snapshots)

        orders_updated = 0
        missing_order_statuses = 0
        terminal_order_events = 0
        errors: list[str] = []

        for snapshot in order_snapshots:
            try:
                status = self.client.get_order_status(snapshot.symbol, snapshot.exchange_order_id)
                if status is None:
                    missing_order_statuses += 1
                    self._record_risk_event(
                        symbol=snapshot.symbol,
                        bot_session_id=snapshot.bot_session_id,
                        event_type="exchange_order_status_missing",
                        severity=AlertSeverity.WARNING.value,
                        reason="Exchange order status was unavailable",
                        payload={"order_id": snapshot.id, "exchange_order_id": snapshot.exchange_order_id},
                    )
                    continue
                self._persist_order_status(snapshot, status)
                orders_updated += 1
                if status.status in {"CANCELED", "EXPIRED", "REJECTED"}:
                    terminal_order_events += 1
                    self._record_terminal_order_event(snapshot, status)
            except Exception as exc:
                message = f"order_id={snapshot.id}: {exc}"
                errors.append(message)
                logger.exception("Exchange order lifecycle reconciliation failed", extra={"order_id": snapshot.id})

        position_counts = self._sync_positions(
            symbols=sorted(symbols_to_sync),
            bot_session_id=bot_session_id,
            cancel_stale_reduce_only=cancel_stale_reduce_only,
        )
        summary = ExchangeLifecycleSummary(
            orders_polled=len(order_snapshots),
            orders_updated=orders_updated,
            missing_order_statuses=missing_order_statuses,
            terminal_order_events=terminal_order_events,
            positions_synced=position_counts.positions_synced,
            drift_events=position_counts.drift_events,
            stale_orders_cancelled=position_counts.stale_orders_cancelled,
            cancel_failures=position_counts.cancel_failures,
            errors=errors,
        )
        logger.info(
            "Exchange lifecycle reconciliation completed",
            extra={
                "orders_polled": summary.orders_polled,
                "orders_updated": summary.orders_updated,
                "missing_order_statuses": summary.missing_order_statuses,
                "terminal_order_events": summary.terminal_order_events,
                "positions_synced": summary.positions_synced,
                "drift_events": summary.drift_events,
                "stale_orders_cancelled": summary.stale_orders_cancelled,
                "cancel_failures": summary.cancel_failures,
                "errors": len(summary.errors),
            },
        )
        return summary

    def _load_order_snapshots(self, *, limit: int) -> list[OrderLifecycleSnapshot]:
        with session_scope(self.session_factory) as session:
            orders = OrderRepository(session).list_exchange_reconcilable(limit=limit)
            return [OrderLifecycleSnapshot.from_model(order) for order in orders]

    def _persist_order_status(self, snapshot: OrderLifecycleSnapshot, status: ExchangeOrderStatus) -> None:
        with session_scope(self.session_factory) as session:
            fill_aggregate = ExchangeFillRepository(session).aggregate_by_order_id(snapshot.exchange_order_id)
            OrderRepository(session).apply_exchange_order_status(
                snapshot.id,
                status,
                fill_aggregate=fill_aggregate,
            )

    def _record_terminal_order_event(
        self,
        snapshot: OrderLifecycleSnapshot,
        status: ExchangeOrderStatus,
    ) -> None:
        severity = AlertSeverity.CRITICAL if snapshot.state in {OrderLifecycleState.PENDING, OrderLifecycleState.ENTRY_PLACED} else AlertSeverity.WARNING
        reason = f"Exchange order reached terminal status {status.status}"
        payload = {
            "order_id": snapshot.id,
            "exchange_order_id": snapshot.exchange_order_id,
            "exchange_status": status.status,
            "protected": snapshot.protected,
        }
        self.alert_queue.enqueue(severity, reason, payload)
        self._record_risk_event(
            symbol=snapshot.symbol,
            bot_session_id=snapshot.bot_session_id,
            event_type="exchange_order_terminal_status",
            severity=severity.value,
            reason=reason,
            payload=payload,
        )

    def _sync_positions(
        self,
        *,
        symbols: list[str],
        bot_session_id: int | None,
        cancel_stale_reduce_only: bool,
    ) -> PositionLifecycleCounts:
        counts = PositionLifecycleCounts()
        for symbol in symbols:
            previous = self._load_open_position_snapshot(symbol)
            exchange_position = self.client.get_open_position(symbol)
            drift = self._detect_position_drift(previous, exchange_position)
            with session_scope(self.session_factory) as session:
                PositionRepository(session).sync_exchange_position(
                    symbol=symbol,
                    position=exchange_position,
                    bot_session_id=bot_session_id if previous is None else previous.bot_session_id,
                )
            counts.positions_synced += 1
            if drift is not None:
                counts.drift_events += 1
                self._record_position_drift(symbol, previous, exchange_position, drift)
            if cancel_stale_reduce_only and exchange_position is None:
                cancelled, failed = self._cancel_stale_reduce_only_orders(symbol, previous)
                counts.stale_orders_cancelled += cancelled
                counts.cancel_failures += failed
        return counts

    def _load_open_position_snapshot(self, symbol: str) -> PositionSnapshot | None:
        with session_scope(self.session_factory) as session:
            model = PositionRepository(session).get_open_by_symbol(symbol)
            if model is None:
                return None
            return PositionSnapshot.from_model(model)

    def _detect_position_drift(
        self,
        previous: PositionSnapshot | None,
        exchange_position: Position | None,
    ) -> str | None:
        if previous is None and exchange_position is None:
            return None
        if previous is None and exchange_position is not None:
            return "exchange_position_without_local_record"
        if previous is not None and exchange_position is None:
            return "local_position_missing_on_exchange"
        if previous is None or exchange_position is None:
            return None
        if previous.side != exchange_position.side.value:
            return "position_side_mismatch"
        if abs(previous.quantity - exchange_position.quantity) > self.quantity_tolerance:
            return "position_quantity_mismatch"
        return None

    def _record_position_drift(
        self,
        symbol: str,
        previous: PositionSnapshot | None,
        exchange_position: Position | None,
        drift_type: str,
    ) -> None:
        severity = AlertSeverity.CRITICAL if drift_type == "exchange_position_without_local_record" else AlertSeverity.WARNING
        payload: dict[str, object] = {
            "drift_type": drift_type,
            "local_position": self._position_snapshot_payload(previous),
            "exchange_position": self._exchange_position_payload(exchange_position),
        }
        reason = f"Position drift detected: {drift_type}"
        self.alert_queue.enqueue(severity, reason, {"symbol": symbol, "drift_type": drift_type})
        self._record_risk_event(
            symbol=symbol,
            bot_session_id=previous.bot_session_id if previous is not None else None,
            event_type="position_drift_detected",
            severity=severity.value,
            reason=reason,
            payload=payload,
        )

    def _cancel_stale_reduce_only_orders(
        self,
        symbol: str,
        previous: PositionSnapshot | None,
    ) -> tuple[int, int]:
        cancelled = 0
        failed = 0
        for order in self.client.get_open_orders(symbol):
            if not self._is_stale_reduce_only_protection(order):
                continue
            exchange_order_id = str(order.get("orderId") or "")
            if not exchange_order_id:
                continue
            result = self.client.cancel_order(symbol, exchange_order_id)
            if result.success:
                cancelled += 1
                event_type = "stale_reduce_only_order_cancelled"
                severity = AlertSeverity.WARNING.value
                reason = "Cancelled stale reduce-only protection order because exchange position is flat"
            else:
                failed += 1
                event_type = "stale_reduce_only_order_cancel_failed"
                severity = AlertSeverity.CRITICAL.value
                reason = "Could not cancel stale reduce-only protection order"
            self._record_risk_event(
                symbol=symbol,
                bot_session_id=previous.bot_session_id if previous is not None else None,
                event_type=event_type,
                severity=severity,
                reason=reason,
                payload={"exchange_order_id": exchange_order_id, "message": result.message, "raw_order": dict(order)},
            )
        return cancelled, failed

    def _is_stale_reduce_only_protection(self, order: dict[str, object]) -> bool:
        order_type = str(order.get("type") or order.get("origType") or "").upper()
        return order_type in {"LIMIT", "STOP", "STOP_MARKET", "TAKE_PROFIT", "TAKE_PROFIT_MARKET"} and self._is_reduce_only(order)

    def _is_reduce_only(self, order: dict[str, object]) -> bool:
        value = order.get("reduceOnly")
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() == "true"
        return False

    def _record_risk_event(
        self,
        *,
        symbol: str,
        bot_session_id: int | None,
        event_type: str,
        severity: str,
        reason: str,
        payload: dict[str, object],
    ) -> None:
        with session_scope(self.session_factory) as session:
            RiskEventRepository(session).create(
                symbol=symbol,
                event_type=event_type,
                severity=severity,
                reason=reason,
                bot_session_id=bot_session_id,
                payload=payload,
            )

    def _position_snapshot_payload(self, position: PositionSnapshot | None) -> dict[str, object]:
        if position is None:
            return {}
        return {
            "id": position.id,
            "symbol": position.symbol,
            "side": position.side,
            "quantity": position.quantity,
            "entry_price": position.entry_price,
        }

    def _exchange_position_payload(self, position: Position | None) -> dict[str, object]:
        if position is None:
            return {}
        return {
            "symbol": position.symbol,
            "side": position.side.value,
            "quantity": position.quantity,
            "entry_price": position.entry_price,
            "unrealized_pnl": position.unrealized_pnl,
            "leverage": position.leverage,
        }


@dataclass
class PositionLifecycleCounts:
    """Mutable counters for position sync and stale-order cancellation."""

    positions_synced: int = 0
    drift_events: int = 0
    stale_orders_cancelled: int = 0
    cancel_failures: int = 0
