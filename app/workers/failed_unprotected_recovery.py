"""Recover persisted orders that were left in FAILED_UNPROTECTED state."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging

from app.persistence.database import SessionFactory, session_scope
from app.persistence.models import OrderModel
from app.persistence.repositories import OrderRepository, RiskEventRepository
from app.workers.reconciliation import ReconciliationOutcome, ReconciliationWorker
from trading_bot.core.types import Signal, SignalSide
from trading_bot.execution.base import ExecutionClient, OrderResult, ProtectedOrderResult
from trading_bot.utils.alerts import AlertQueue, AlertSeverity

logger = logging.getLogger("trading_bot.failed_unprotected_recovery")


@dataclass(frozen=True)
class UnprotectedOrderSnapshot:
    """Database order fields needed to safely attempt recovery outside a DB session."""

    id: int
    bot_session_id: int | None
    symbol: str
    side: str
    quantity: float | None
    exchange_order_id: str | None
    avg_price: float | None
    stop_order_id: str | None
    take_profit_order_id: str | None

    @classmethod
    def from_model(cls, model: OrderModel) -> UnprotectedOrderSnapshot:
        return cls(
            id=model.id,
            bot_session_id=model.bot_session_id,
            symbol=model.symbol,
            side=model.side,
            quantity=model.quantity,
            exchange_order_id=model.exchange_order_id,
            avg_price=model.avg_price,
            stop_order_id=model.stop_order_id,
            take_profit_order_id=model.take_profit_order_id,
        )


@dataclass(frozen=True)
class FailedUnprotectedRecoverySummary:
    """Summary of one recovery sweep."""

    scanned: int = 0
    recovered: int = 0
    emergency_closed: int = 0
    manual_review: int = 0
    errors: list[str] = field(default_factory=list)


class FailedUnprotectedRecoveryWorker:
    """Retry protection verification and emergency-close persisted unsafe orders."""

    def __init__(
        self,
        *,
        session_factory: SessionFactory,
        client: ExecutionClient,
        alert_queue: AlertQueue,
        max_attempts: int = 3,
        backoff_seconds: float = 1.0,
    ) -> None:
        self.session_factory = session_factory
        self.client = client
        self.alert_queue = alert_queue
        self.reconciliation_worker = ReconciliationWorker(
            client,
            alert_queue,
            max_attempts=max_attempts,
            backoff_seconds=backoff_seconds,
        )

    def recover_once(self, *, limit: int = 100) -> FailedUnprotectedRecoverySummary:
        snapshots = self._load_recovery_snapshots(limit=limit)
        recovered = 0
        emergency_closed = 0
        manual_review = 0
        errors: list[str] = []

        for snapshot in snapshots:
            try:
                outcome = self._recover_snapshot(snapshot)
                if outcome is None:
                    manual_review += 1
                    continue
                if outcome.protected_order.protected:
                    recovered += 1
                elif outcome.emergency_close_success:
                    emergency_closed += 1
                else:
                    manual_review += 1
            except Exception as exc:
                message = f"order_id={snapshot.id}: {exc}"
                errors.append(message)
                logger.exception("Failed unprotected order recovery error", extra={"order_id": snapshot.id})

        summary = FailedUnprotectedRecoverySummary(
            scanned=len(snapshots),
            recovered=recovered,
            emergency_closed=emergency_closed,
            manual_review=manual_review,
            errors=errors,
        )
        logger.info(
            "Failed unprotected order recovery completed",
            extra={
                "scanned": summary.scanned,
                "recovered": summary.recovered,
                "emergency_closed": summary.emergency_closed,
                "manual_review": summary.manual_review,
                "errors": len(summary.errors),
            },
        )
        return summary

    def _load_recovery_snapshots(self, *, limit: int) -> list[UnprotectedOrderSnapshot]:
        with session_scope(self.session_factory) as session:
            orders = OrderRepository(session).list_unprotected_for_recovery(limit=limit)
            return [UnprotectedOrderSnapshot.from_model(order) for order in orders]

    def _recover_snapshot(self, snapshot: UnprotectedOrderSnapshot) -> ReconciliationOutcome | None:
        side = self._coerce_side(snapshot.side)
        if side is None or snapshot.quantity is None or snapshot.quantity <= 0:
            reason = "Cannot recover unprotected order without valid side and quantity"
            self.alert_queue.enqueue(
                AlertSeverity.EMERGENCY,
                reason,
                {"order_id": snapshot.id, "symbol": snapshot.symbol},
            )
            self._record_manual_review_required(snapshot, reason=reason)
            return None

        order_result = OrderResult(
            success=True,
            order_id=snapshot.exchange_order_id,
            avg_price=snapshot.avg_price,
            quantity=snapshot.quantity,
            message="recovering persisted failed-unprotected order",
            protected_order=ProtectedOrderResult(
                entry_order_id=snapshot.exchange_order_id,
                stop_order_id=snapshot.stop_order_id,
                take_profit_order_id=snapshot.take_profit_order_id,
                protected=False,
                requires_manual_review=True,
                message="recovering persisted failed-unprotected order",
            ),
        )
        signal = Signal(
            side=side,
            entry_price=snapshot.avg_price or 0.0,
            stop_price=0.0,
            take_profit_price=0.0,
            quantity=snapshot.quantity,
            timestamp=datetime.now(timezone.utc),
        )
        outcome = self.reconciliation_worker.reconcile(
            symbol=snapshot.symbol,
            signal=signal,
            order_result=order_result,
        )
        self._persist_recovery_outcome(snapshot, outcome)
        return outcome

    def _persist_recovery_outcome(
        self,
        snapshot: UnprotectedOrderSnapshot,
        outcome: ReconciliationOutcome,
    ) -> None:
        with session_scope(self.session_factory) as session:
            OrderRepository(session).apply_protected_order_result(
                snapshot.id,
                outcome.protected_order,
                emergency_close_order_id=outcome.emergency_close_order_id,
            )
            risk_events = RiskEventRepository(session)
            for event in outcome.events:
                payload = dict(event.payload)
                payload["attempts"] = outcome.attempts
                payload["order_id"] = snapshot.id
                payload["recovery"] = True
                risk_events.create(
                    symbol=snapshot.symbol,
                    event_type=f"failed_unprotected_recovery_{event.event_type}",
                    severity=event.severity,
                    reason=event.reason,
                    bot_session_id=snapshot.bot_session_id,
                    payload=payload,
                )

    def _record_manual_review_required(self, snapshot: UnprotectedOrderSnapshot, *, reason: str) -> None:
        with session_scope(self.session_factory) as session:
            risk_events = RiskEventRepository(session)
            risk_events.create(
                symbol=snapshot.symbol,
                event_type="failed_unprotected_recovery_manual_review",
                severity=AlertSeverity.EMERGENCY.value,
                reason=reason,
                bot_session_id=snapshot.bot_session_id,
                payload={"order_id": snapshot.id, "side": snapshot.side, "quantity": snapshot.quantity},
            )

    def _coerce_side(self, side: str) -> SignalSide | None:
        normalized = side.upper()
        if normalized == SignalSide.LONG.value:
            return SignalSide.LONG
        if normalized == SignalSide.SHORT.value:
            return SignalSide.SHORT
        return None
