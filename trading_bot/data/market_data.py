"""Market data cleaning and validation helpers."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class MarketDataQualityReport:
    """Summary of cleaning actions applied to OHLCV data."""

    input_rows: int
    output_rows: int
    duplicates_removed: int
    missing_candles: int
    first_time: str
    last_time: str


def clean_ohlcv(candles: pd.DataFrame, *, timeframe: str) -> tuple[pd.DataFrame, MarketDataQualityReport]:
    """Normalize, deduplicate, and sort OHLCV candles."""
    required = ["time", "open", "high", "low", "close", "volume"]
    missing = [column for column in required if column not in candles.columns]
    if missing:
        raise ValueError(f"Missing OHLCV columns: {', '.join(missing)}")
    input_rows = len(candles)
    df = candles.loc[:, required].copy()
    df["time"] = pd.to_datetime(df["time"], utc=True)
    for column in ["open", "high", "low", "close", "volume"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df = df.dropna(subset=required)
    df = df[df["volume"] >= 0]
    df = df.sort_values("time").drop_duplicates(subset=["time"], keep="last").reset_index(drop=True)
    duplicates_removed = input_rows - len(df)
    missing_candles = count_missing_candles(df, timeframe=timeframe)
    first_time = df.iloc[0]["time"].isoformat() if len(df) else ""
    last_time = df.iloc[-1]["time"].isoformat() if len(df) else ""
    return df, MarketDataQualityReport(
        input_rows=input_rows,
        output_rows=len(df),
        duplicates_removed=max(0, duplicates_removed),
        missing_candles=missing_candles,
        first_time=first_time,
        last_time=last_time,
    )


def count_missing_candles(candles: pd.DataFrame, *, timeframe: str) -> int:
    """Return the number of expected candle slots missing from a sorted DataFrame."""
    if len(candles) < 2:
        return 0
    freq = _pandas_frequency(timeframe)
    expected = pd.date_range(candles.iloc[0]["time"], candles.iloc[-1]["time"], freq=freq)
    return max(0, len(expected) - len(candles))


def _pandas_frequency(timeframe: str) -> str:
    normalized = timeframe.strip().lower()
    if normalized.endswith("m"):
        return f"{int(normalized[:-1])}min"
    if normalized.endswith("h"):
        return f"{int(normalized[:-1])}h"
    if normalized.endswith("d"):
        return f"{int(normalized[:-1])}D"
    raise ValueError(f"Unsupported timeframe: {timeframe}")
