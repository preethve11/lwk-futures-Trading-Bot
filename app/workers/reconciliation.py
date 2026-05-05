"""Post-entry protection reconciliation and emergency close handling."""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
import time
from typing import Callable

from trading_bot.core.types import Signal, SignalSide
from trading_bot.execution.base import ExecutionClient, OrderResult, ProtectedOrderResult
from trading_bot.utils.alerts import AlertQueue, AlertSeverity

logger = logging.getLogger("trading_bot.reconciliation")

SleepFn = Callable[[float], None]


@dataclass(frozen=True)
class ReconciliationEvent:
    """Safety event emitted during order protection reconciliation."""

    event_type: str
    severity: str
    reason: str
    payload: dict[str, object] = field(default_factory=dict)


@dataclass
class ReconciliationOutcome:
    """Final reconciliation result and events to persist."""

    protected_order: ProtectedOrderResult
    attempts: int
    emergency_close_order_id: str | None = None
    emergency_close_success: bool = False
    events: list[ReconciliationEvent] = field(default_factory=list)


class ReconciliationWorker:
    """Verifies SL/TP protection after entry and closes unprotected positions."""

    def __init__(
        self,
        client: ExecutionClient,
        alert_queue: AlertQueue,
        *,
        max_attempts: int = 3,
        backoff_seconds: float = 1.0,
        sleep_fn: SleepFn = time.sleep,
    ) -> None:
        if max_attempts <= 0:
            raise ValueError("max_attempts must be positive")
        self.client = client
        self.alert_queue = alert_queue
        self.max_attempts = max_attempts
        self.backoff_seconds = backoff_seconds
        self.sleep_fn = sleep_fn

    def reconcile(
        self,
        *,
        symbol: str,
        signal: Signal,
        order_result: OrderResult,
    ) -> ReconciliationOutcome:
        """Verify protection and emergency-close when SL/TP orders are missing."""
        protected_order = self._initial_protected_order(order_result)
        events: list[ReconciliationEvent] = []

        if not order_result.success:
            message = order_result.message or "entry order failed"
            event = ReconciliationEvent(
                event_type="entry_order_failed",
                severity=AlertSeverity.CRITICAL.value,
                reason=message,
                payload={"symbol": symbol},
            )
            events.append(event)
            self.alert_queue.enqueue(AlertSeverity.CRITICAL, message, {"symbol": symbol})
            protected_order.requires_manual_review = True
            protected_order.message = message
            return ReconciliationOutcome(protected_order=protected_order, attempts=0, events=events)

        last_missing: list[str] = []
        for attempt in range(1, self.max_attempts + 1):
            open_orders = self.client.get_open_orders(symbol)
            verification = self._verify_protection(symbol, signal.side, protected_order, open_orders)
            last_missing = verification.missing
            events.append(
                ReconciliationEvent(
                    event_type="reconciliation_attempt",
                    severity=AlertSeverity.INFO.value if verification.protected else AlertSeverity.WARNING.value,
                    reason="protection verified" if verification.protected else "protection missing",
                    payload={
                        "attempt": attempt,
                        "missing": ",".join(verification.missing),
                        "stop_order_id": verification.stop_order_id or "",
                        "take_profit_order_id": verification.take_profit_order_id or "",
                    },
                )
            )

            if verification.protected:
                protected_order.stop_order_id = verification.stop_order_id
                protected_order.take_profit_order_id = verification.take_profit_order_id
                protected_order.protected = True
                protected_order.requires_manual_review = False
                protected_order.message = "SL/TP protection verified"
                self.alert_queue.enqueue(
                    AlertSeverity.INFO,
                    "Order protection verified",
                    {"symbol": symbol, "entry_order_id": protected_order.entry_order_id or ""},
                )
                return ReconciliationOutcome(protected_order=protected_order, attempts=attempt, events=events)

            self.alert_queue.enqueue(
                AlertSeverity.WARNING,
                "Order protection missing",
                {"symbol": symbol, "attempt": attempt, "missing": ",".join(verification.missing)},
            )
            if attempt < self.max_attempts:
                self.sleep_fn(self.backoff_seconds * attempt)

        missing_text = ",".join(last_missing) if last_missing else "unknown"
        critical_message = "Order remains unprotected after reconciliation retries"
        self.alert_queue.enqueue(AlertSeverity.CRITICAL, critical_message, {"symbol": symbol, "missing": missing_text})
        events.append(
            ReconciliationEvent(
                event_type="manual_review_required",
                severity=AlertSeverity.CRITICAL.value,
                reason=critical_message,
                payload={"missing": missing_text},
            )
        )

        close_result = self.client.emergency_close_position(symbol, signal.side, signal.quantity)
        emergency_reason = "Emergency market close submitted" if close_result.success else "Emergency market close failed"
        emergency_severity = AlertSeverity.EMERGENCY.value
        self.alert_queue.enqueue(
            AlertSeverity.EMERGENCY,
            emergency_reason,
            {"symbol": symbol, "close_order_id": close_result.order_id or "", "success": close_result.success},
        )
        events.append(
            ReconciliationEvent(
                event_type="emergency_close",
                severity=emergency_severity,
                reason=emergency_reason,
                payload={
                    "close_order_id": close_result.order_id or "",
                    "success": close_result.success,
                    "message": close_result.message,
                },
            )
        )
        protected_order.protected = False
        protected_order.requires_manual_review = True
        protected_order.message = f"{critical_message}; {emergency_reason}"
        return ReconciliationOutcome(
            protected_order=protected_order,
            attempts=self.max_attempts,
            emergency_close_order_id=close_result.order_id,
            emergency_close_success=close_result.success,
            events=events,
        )

    def _initial_protected_order(self, order_result: OrderResult) -> ProtectedOrderResult:
        if order_result.protected_order is not None:
            return order_result.protected_order
        return ProtectedOrderResult(entry_order_id=order_result.order_id, message=order_result.message)

    def _verify_protection(
        self,
        symbol: str,
        entry_side: SignalSide,
        protected_order: ProtectedOrderResult,
        open_orders: list[dict[str, object]],
    ) -> ProtectionVerification:
        close_side = "SELL" if entry_side == SignalSide.LONG else "BUY"
        stop_order_id = self._find_order_id(
            open_orders,
            known_order_id=protected_order.stop_order_id,
            close_side=close_side,
            accepted_types={"STOP", "STOP_MARKET"},
        )
        take_profit_order_id = self._find_order_id(
            open_orders,
            known_order_id=protected_order.take_profit_order_id,
            close_side=close_side,
            accepted_types={"LIMIT", "TAKE_PROFIT", "TAKE_PROFIT_MARKET"},
        )
        missing = []
        if stop_order_id is None:
            missing.append("stop_loss")
        if take_profit_order_id is None:
            missing.append("take_profit")
        return ProtectionVerification(
            protected=not missing,
            missing=missing,
            stop_order_id=stop_order_id,
            take_profit_order_id=take_profit_order_id,
        )

    def _find_order_id(
        self,
        open_orders: list[dict[str, object]],
        *,
        known_order_id: str | None,
        close_side: str,
        accepted_types: set[str],
    ) -> str | None:
        for order in open_orders:
            order_id = str(order.get("orderId", ""))
            order_type = str(order.get("type") or order.get("origType") or "").upper()
            side = str(order.get("side") or "").upper()
            if known_order_id is not None and order_id == known_order_id:
                return order_id
            if order_type in accepted_types and side == close_side and self._is_reduce_only(order):
                return order_id
        return None

    def _is_reduce_only(self, order: dict[str, object]) -> bool:
        value = order.get("reduceOnly")
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() == "true"
        return False


@dataclass(frozen=True)
class ProtectionVerification:
    """Single-attempt protection verification detail."""

    protected: bool
    missing: list[str]
    stop_order_id: str | None = None
    take_profit_order_id: str | None = None
