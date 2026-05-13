"""Bridge DataFrames into the SQLAlchemy research repositories."""

from __future__ import annotations

from datetime import datetime
from typing import cast

import pandas as pd

from app.persistence.repositories import FeatureRepository, MarketDataRepository, RegimeRepository
from trading_bot.features.feature_library import DEFAULT_FEATURE_VERSION, feature_payload


def persist_market_data(
    repository: MarketDataRepository,
    candles: pd.DataFrame,
    *,
    symbol: str,
    timeframe: str,
    source: str,
) -> int:
    """Persist OHLCV rows and return the number of rows processed."""
    count = 0
    for _, row in candles.iterrows():
        repository.upsert_candle(
            symbol=symbol,
            timeframe=timeframe,
            open_time=_row_datetime(row["time"]),
            open_price=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row["volume"]),
            source=source,
            is_closed=True,
        )
        count += 1
    return count


def persist_feature_frame(
    repository: FeatureRepository,
    features: pd.DataFrame,
    *,
    symbol: str,
    timeframe: str,
    feature_set_version: str = DEFAULT_FEATURE_VERSION,
) -> int:
    """Persist feature payloads from a feature-enriched DataFrame."""
    count = 0
    for _, row in features.iterrows():
        repository.upsert_features(
            symbol=symbol,
            timeframe=timeframe,
            event_time=_row_datetime(row["time"]),
            feature_set_version=feature_set_version,
            payload=feature_payload(row),
        )
        count += 1
    return count


def persist_regime_frame(
    repository: RegimeRepository,
    regimes: pd.DataFrame,
    *,
    symbol: str,
    timeframe: str,
) -> int:
    """Persist regime labels from a regime-enriched DataFrame."""
    count = 0
    for _, row in regimes.iterrows():
        repository.upsert_regime(
            symbol=symbol,
            timeframe=timeframe,
            event_time=_row_datetime(row["time"]),
            trend_state=str(row["trend_state"]),
            volatility_state=str(row["volatility_state"]),
            liquidity_state=str(row["liquidity_state"]),
            regime_id=str(row["regime_id"]),
            detector_version=str(row.get("regime_detector_version", "v1")),
            payload=feature_payload(row),
        )
        count += 1
    return count


def _row_datetime(value: object) -> datetime:
    if isinstance(value, pd.Timestamp):
        return cast(datetime, value.to_pydatetime())
    if isinstance(value, datetime):
        return value
    return cast(datetime, pd.Timestamp(value).to_pydatetime())
