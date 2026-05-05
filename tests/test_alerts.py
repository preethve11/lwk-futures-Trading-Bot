from __future__ import annotations

import time

from trading_bot.utils.alerts import AlertQueue, AlertSeverity, format_alert


def test_alert_severity_formatting() -> None:
    text = format_alert(AlertSeverity.EMERGENCY, "Manual review required", {"symbol": "ZECUSDT"})

    assert text == "[EMERGENCY] Manual review required | symbol=ZECUSDT"


def test_alert_queue_does_not_block_on_slow_sender() -> None:
    sent: list[str] = []

    def slow_sender(text: str, bot_token: str, chat_id: str) -> bool:
        time.sleep(0.2)
        sent.append(text)
        return True

    queue = AlertQueue(sender=slow_sender, autostart=True)

    started = time.perf_counter()
    queued = queue.enqueue(AlertSeverity.CRITICAL, "Protection missing")
    elapsed = time.perf_counter() - started

    assert queued is True
    assert elapsed < 0.05
    queue.stop(drain=True)
    assert sent == ["[CRITICAL] Protection missing"]
