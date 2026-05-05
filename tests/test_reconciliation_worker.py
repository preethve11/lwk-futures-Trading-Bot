from __future__ import annotations

from datetime import datetime, timezone

from app.workers.reconciliation import ReconciliationWorker
from trading_bot.core.types import Signal, SignalSide
from trading_bot.execution.base import OrderResult, ProtectedOrderResult
from trading_bot.utils.alerts import AlertQueue


class FakeExecutionClient:
    def __init__(
        self,
        open_order_batches: list[list[dict[str, object]]],
        close_result: OrderResult | None = None,
    ) -> None:
        self.open_order_batches = open_order_batches
        self.close_result = close_result or OrderResult(success=True, order_id="close-1")
        self.open_order_calls = 0
        self.close_calls = 0

    def get_open_orders(self, symbol: str) -> list[dict[str, object]]:
        self.open_order_calls += 1
        if self.open_order_calls <= len(self.open_order_batches):
            return self.open_order_batches[self.open_order_calls - 1]
        return self.open_order_batches[-1]

    def emergency_close_position(self, symbol: str, side: SignalSide, quantity: float) -> OrderResult:
        self.close_calls += 1
        return self.close_result


def _signal() -> Signal:
    return Signal(
        side=SignalSide.LONG,
        entry_price=100.0,
        stop_price=99.0,
        take_profit_price=102.0,
        quantity=0.5,
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _order_result() -> OrderResult:
    return OrderResult(
        success=True,
        order_id="entry-1",
        avg_price=100.0,
        quantity=0.5,
        protected_order=ProtectedOrderResult(
            entry_order_id="entry-1",
            stop_order_id="sl-1",
            take_profit_order_id="tp-1",
        ),
    )


def _protected_orders() -> list[dict[str, object]]:
    return [
        {"orderId": "tp-1", "type": "LIMIT", "side": "SELL", "reduceOnly": True},
        {"orderId": "sl-1", "type": "STOP_MARKET", "side": "SELL", "reduceOnly": True},
    ]


def _alert_queue(sent: list[str]) -> AlertQueue:
    def sender(text: str, bot_token: str, chat_id: str) -> bool:
        sent.append(text)
        return True

    return AlertQueue(sender=sender, autostart=True)


def test_reconciliation_protected_order_success() -> None:
    sent: list[str] = []
    queue = _alert_queue(sent)
    client = FakeExecutionClient([_protected_orders()])
    worker = ReconciliationWorker(client, queue, backoff_seconds=0)

    outcome = worker.reconcile(symbol="ZECUSDT", signal=_signal(), order_result=_order_result())

    queue.stop(drain=True)
    assert outcome.protected_order.protected is True
    assert outcome.protected_order.requires_manual_review is False
    assert outcome.attempts == 1
    assert client.close_calls == 0
    assert [event.event_type for event in outcome.events] == ["reconciliation_attempt"]
    assert any("[INFO] Order protection verified" in message for message in sent)


def test_reconciliation_retries_missing_protection_until_verified() -> None:
    sent: list[str] = []
    sleeps: list[float] = []
    queue = _alert_queue(sent)
    client = FakeExecutionClient([[], _protected_orders()])
    worker = ReconciliationWorker(client, queue, backoff_seconds=0.25, sleep_fn=sleeps.append)

    outcome = worker.reconcile(symbol="ZECUSDT", signal=_signal(), order_result=_order_result())

    queue.stop(drain=True)
    assert outcome.protected_order.protected is True
    assert outcome.attempts == 2
    assert client.close_calls == 0
    assert sleeps == [0.25]
    assert any("[WARNING] Order protection missing" in message for message in sent)


def test_reconciliation_emergency_closes_failed_protection() -> None:
    sent: list[str] = []
    sleeps: list[float] = []
    queue = _alert_queue(sent)
    client = FakeExecutionClient([[], [], []], close_result=OrderResult(success=True, order_id="close-99"))
    worker = ReconciliationWorker(client, queue, backoff_seconds=0.1, sleep_fn=sleeps.append)

    outcome = worker.reconcile(symbol="ZECUSDT", signal=_signal(), order_result=_order_result())

    queue.stop(drain=True)
    assert outcome.protected_order.protected is False
    assert outcome.protected_order.requires_manual_review is True
    assert outcome.emergency_close_order_id == "close-99"
    assert outcome.emergency_close_success is True
    assert client.close_calls == 1
    assert sleeps == [0.1, 0.2]
    assert [event.event_type for event in outcome.events].count("reconciliation_attempt") == 3
    assert "manual_review_required" in [event.event_type for event in outcome.events]
    assert "emergency_close" in [event.event_type for event in outcome.events]
    assert any("[EMERGENCY] Emergency market close submitted" in message for message in sent)
