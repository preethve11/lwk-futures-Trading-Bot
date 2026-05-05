"""Non-blocking alert queue with Telegram severity formatting."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import logging
from queue import Full, Queue
from threading import Lock, Thread
from typing import Callable, Optional

from trading_bot.utils.telegram import send_telegram

logger = logging.getLogger("trading_bot.utils.alerts")

AlertSender = Callable[[str, str, str], bool]


class AlertSeverity(str, Enum):
    """Operational alert severity levels."""

    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    EMERGENCY = "EMERGENCY"


@dataclass(frozen=True)
class Alert:
    """Queued alert message."""

    severity: AlertSeverity
    text: str
    context: dict[str, object] = field(default_factory=dict)


def format_alert(severity: AlertSeverity, text: str, context: Optional[dict[str, object]] = None) -> str:
    """Format alert text with severity and compact structured context."""
    formatted = f"[{severity.value}] {text}"
    if context:
        details = " ".join(f"{key}={value}" for key, value in sorted(context.items()))
        formatted = f"{formatted} | {details}"
    return formatted


class AlertQueue:
    """In-process queue that keeps Telegram network I/O off the trading path."""

    def __init__(
        self,
        *,
        bot_token: str = "",
        chat_id: str = "",
        sender: AlertSender = send_telegram,
        maxsize: int = 1000,
        autostart: bool = True,
    ) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.sender = sender
        self._queue: Queue[Alert | None] = Queue(maxsize=maxsize)
        self._lock = Lock()
        self._thread: Thread | None = None
        if autostart:
            self.start()

    def start(self) -> None:
        """Start the background sender thread once."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._thread = Thread(target=self._run, name="trading-bot-alerts", daemon=True)
            self._thread.start()

    def enqueue(
        self,
        severity: AlertSeverity,
        text: str,
        context: Optional[dict[str, object]] = None,
    ) -> bool:
        """Queue an alert without blocking the caller."""
        try:
            self._queue.put_nowait(Alert(severity=severity, text=text, context=context or {}))
            return True
        except Full:
            logger.warning("Alert queue full, dropping alert", extra={"severity": severity.value})
            return False

    def stop(self, *, drain: bool = True, timeout: float = 2.0) -> None:
        """Stop the background thread."""
        if drain:
            self._queue.join()
        self._queue.put(None)
        thread = self._thread
        if thread is not None:
            thread.join(timeout=timeout)

    def _run(self) -> None:
        while True:
            alert = self._queue.get()
            try:
                if alert is None:
                    return
                text = format_alert(alert.severity, alert.text, alert.context)
                self.sender(text, self.bot_token, self.chat_id)
            except Exception as exc:
                logger.exception("Alert sender failed", extra={"error": str(exc)})
            finally:
                self._queue.task_done()
