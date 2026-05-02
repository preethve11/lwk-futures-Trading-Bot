"""Historical OHLCV data loaders for backtesting."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

import pandas as pd

REQUIRED_OHLCV_COLUMNS = ("time", "open", "high", "low", "close", "volume")


class BinanceKlineClient(Protocol):
    """Subset of the python-binance futures client used by the loader."""

    def futures_klines(
        self,
        *,
        symbol: str,
        interval: str,
        startTime: int | None = None,
        endTime: int | None = None,
        limit: int = 1500,
    ) -> list[list[object]]:
        """Return raw Binance futures kline rows."""
        ...


@dataclass(frozen=True)
class DateRange:
    """Inclusive UTC date range used for historical loading."""

    start: str | None = None
    end: str | None = None

    @property
    def start_ms(self) -> int | None:
        if self.start is None:
            return None
        return int(_to_utc_timestamp(self.start).timestamp() * 1000)

    @property
    def end_ms(self) -> int | None:
        if self.end is None:
            return None
        return int(_to_utc_timestamp(self.end).timestamp() * 1000)


def _to_utc_timestamp(value: str | pd.Timestamp) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def _normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    missing = [column for column in REQUIRED_OHLCV_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"OHLCV data missing required columns: {', '.join(missing)}")

    normalized = df.loc[:, REQUIRED_OHLCV_COLUMNS].copy()
    normalized["time"] = pd.to_datetime(normalized["time"], utc=True)
    for column in ("open", "high", "low", "close", "volume"):
        normalized[column] = pd.to_numeric(normalized[column], errors="raise")
    return normalized.sort_values("time").reset_index(drop=True)


def _filter_range(df: pd.DataFrame, date_range: DateRange) -> pd.DataFrame:
    filtered = df
    if date_range.start is not None:
        filtered = filtered[filtered["time"] >= _to_utc_timestamp(date_range.start)]
    if date_range.end is not None:
        filtered = filtered[filtered["time"] <= _to_utc_timestamp(date_range.end)]
    return filtered.reset_index(drop=True)


def load_csv_ohlcv(path: str | Path, *, start: str | None = None, end: str | None = None) -> pd.DataFrame:
    """Load OHLCV candles from a local CSV file and optionally filter by date."""
    csv_path = Path(path)
    if not csv_path.exists():
        raise FileNotFoundError(f"Historical data CSV not found: {csv_path}")
    df = _normalize_ohlcv(pd.read_csv(csv_path))
    return _filter_range(df, DateRange(start=start, end=end))


class BinanceHistoricalDataLoader:
    """Load Binance USDT-M futures candles over a historical date range."""

    def __init__(self, client: BinanceKlineClient, *, request_limit: int = 1500, pause_seconds: float = 0.2) -> None:
        if request_limit <= 0 or request_limit > 1500:
            raise ValueError("request_limit must be between 1 and 1500")
        self.client = client
        self.request_limit = request_limit
        self.pause_seconds = pause_seconds

    def load_klines(
        self,
        *,
        symbol: str,
        interval: str,
        start: str | None = None,
        end: str | None = None,
    ) -> pd.DataFrame:
        """Fetch candles from Binance and return normalized OHLCV rows."""
        date_range = DateRange(start=start, end=end)
        start_ms = date_range.start_ms
        end_ms = date_range.end_ms
        rows: list[list[object]] = []

        while True:
            batch = self.client.futures_klines(
                symbol=symbol,
                interval=interval,
                startTime=start_ms,
                endTime=end_ms,
                limit=self.request_limit,
            )
            if not batch:
                break

            rows.extend(batch)
            last_open_time = int(cast(str | bytes | bytearray | int, batch[-1][0]))
            next_start_ms = last_open_time + 1
            if start_ms is not None and next_start_ms <= start_ms:
                break
            start_ms = next_start_ms

            if len(batch) < self.request_limit:
                break
            if end_ms is not None and start_ms > end_ms:
                break
            if self.pause_seconds > 0:
                time.sleep(self.pause_seconds)

        if not rows:
            return pd.DataFrame(columns=REQUIRED_OHLCV_COLUMNS)

        raw = pd.DataFrame(
            rows,
            columns=[
                "open_time",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "close_time",
                "quote_asset_volume",
                "number_of_trades",
                "taker_buy_base_volume",
                "taker_buy_quote_volume",
                "ignore",
            ],
        )
        raw["time"] = pd.to_datetime(raw["open_time"], unit="ms", utc=True)
        normalized = _normalize_ohlcv(raw)
        return _filter_range(normalized, date_range)
