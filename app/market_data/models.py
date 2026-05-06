"""Typed market data events used by stream publishers and strategy consumers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class KlineEvent:
    """Normalized Binance kline stream event."""

    symbol: str
    interval: str
    open_time: datetime
    close_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    is_closed: bool
    event_time: datetime

    @classmethod
    def from_binance_message(cls, message: dict[str, Any]) -> KlineEvent:
        """Create an event from a combined or raw Binance kline stream payload."""
        payload = message.get("data", message)
        if not isinstance(payload, dict):
            raise ValueError("Binance kline payload must be an object")
        kline = payload.get("k")
        if not isinstance(kline, dict):
            raise ValueError("Binance kline payload is missing field 'k'")

        symbol = str(kline.get("s") or payload.get("s") or "").upper()
        interval = str(kline.get("i") or "")
        if not symbol or not interval:
            raise ValueError("Binance kline payload is missing symbol or interval")

        return cls(
            symbol=symbol,
            interval=interval,
            open_time=_from_millis(kline["t"]),
            close_time=_from_millis(kline["T"]),
            open=float(kline["o"]),
            high=float(kline["h"]),
            low=float(kline["l"]),
            close=float(kline["c"]),
            volume=float(kline["v"]),
            is_closed=bool(kline["x"]),
            event_time=_from_millis(payload.get("E", kline["T"])),
        )

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> KlineEvent:
        """Create an event from a JSON payload emitted by this application."""
        return cls(
            symbol=str(payload["symbol"]).upper(),
            interval=str(payload["interval"]),
            open_time=_from_iso(str(payload["open_time"])),
            close_time=_from_iso(str(payload["close_time"])),
            open=float(payload["open"]),
            high=float(payload["high"]),
            low=float(payload["low"]),
            close=float(payload["close"]),
            volume=float(payload["volume"]),
            is_closed=bool(payload["is_closed"]),
            event_time=_from_iso(str(payload["event_time"])),
        )

    def to_payload(self) -> dict[str, object]:
        """Serialize the event for Redis pub/sub and list storage."""
        return {
            "symbol": self.symbol,
            "interval": self.interval,
            "open_time": self.open_time.isoformat(),
            "close_time": self.close_time.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "is_closed": self.is_closed,
            "event_time": self.event_time.isoformat(),
        }


def events_to_dataframe(events: list[KlineEvent]) -> pd.DataFrame:
    """Convert normalized kline events to the OHLCV DataFrame shape used by strategies."""
    ordered = sorted(events, key=lambda event: event.open_time)
    return pd.DataFrame(
        [
            {
                "time": event.open_time,
                "open": event.open,
                "high": event.high,
                "low": event.low,
                "close": event.close,
                "volume": event.volume,
            }
            for event in ordered
        ],
        columns=["time", "open", "high", "low", "close", "volume"],
    )


def _from_millis(value: Any) -> datetime:
    return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)


def _from_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
