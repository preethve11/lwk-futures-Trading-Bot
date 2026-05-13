"""Professional market regime detector for research and live attribution."""

from __future__ import annotations

from enum import Enum

import numpy as np
import pandas as pd

from trading_bot.features.feature_library import build_feature_frame


class TrendState(str, Enum):
    """ADX/trend-strength regime labels."""

    STRONG_TREND = "STRONG_TREND"
    WEAK_TREND = "WEAK_TREND"
    RANGING = "RANGING"


class VolatilityState(str, Enum):
    """Realized-volatility percentile regime labels."""

    HIGH_VOL = "HIGH_VOL"
    MEDIUM_VOL = "MEDIUM_VOL"
    LOW_VOL = "LOW_VOL"


class LiquidityState(str, Enum):
    """Volume/spread-proxy liquidity regime labels."""

    HIGH_LIQ = "HIGH_LIQ"
    LOW_LIQ = "LOW_LIQ"


def add_professional_regime_labels(
    candles: pd.DataFrame,
    *,
    detector_version: str = "v1",
    shift_features: bool = True,
    strong_adx: float = 30.0,
    weak_adx: float = 20.0,
) -> pd.DataFrame:
    """Return candles with trend, volatility, liquidity, and combined regime labels."""
    enriched = build_feature_frame(candles, shift_features=shift_features)
    if enriched.empty:
        enriched["trend_state"] = pd.Series(dtype=str)
        enriched["volatility_state"] = pd.Series(dtype=str)
        enriched["liquidity_state"] = pd.Series(dtype=str)
        enriched["regime_id"] = pd.Series(dtype=str)
        enriched["regime_detector_version"] = detector_version
        return enriched
    adx = enriched["adx_14"].fillna(0.0)
    trend_strength = enriched["trend_strength"].abs().fillna(0.0)
    enriched["trend_state"] = np.select(
        [(adx >= strong_adx) & (trend_strength > 0.002), adx >= weak_adx],
        [TrendState.STRONG_TREND.value, TrendState.WEAK_TREND.value],
        default=TrendState.RANGING.value,
    )
    vol_pct = enriched["volatility_percentile_100"].fillna(0.5)
    enriched["volatility_state"] = np.select(
        [vol_pct >= 0.67, vol_pct <= 0.33],
        [VolatilityState.HIGH_VOL.value, VolatilityState.LOW_VOL.value],
        default=VolatilityState.MEDIUM_VOL.value,
    )
    volume_ratio = enriched["volume_ratio_20"].fillna(1.0)
    spread_proxy = enriched["spread_proxy_bps"].fillna(enriched["spread_proxy_bps"].median())
    spread_threshold = float(spread_proxy.rolling(100, min_periods=10).quantile(0.75).fillna(spread_proxy.median()).iloc[-1])
    enriched["liquidity_state"] = np.where(
        (volume_ratio >= 1.0) & (spread_proxy <= spread_threshold),
        LiquidityState.HIGH_LIQ.value,
        LiquidityState.LOW_LIQ.value,
    )
    enriched["regime_id"] = (
        enriched["trend_state"].astype(str)
        + "_"
        + enriched["volatility_state"].astype(str)
        + "_"
        + enriched["liquidity_state"].astype(str)
    )
    enriched["regime_detector_version"] = detector_version
    return enriched


def latest_regime(candles: pd.DataFrame) -> dict[str, str]:
    """Return the latest combined regime as a JSON-safe dictionary."""
    labeled = add_professional_regime_labels(candles)
    if labeled.empty:
        return {
            "trend_state": TrendState.RANGING.value,
            "volatility_state": VolatilityState.MEDIUM_VOL.value,
            "liquidity_state": LiquidityState.LOW_LIQ.value,
            "regime_id": f"{TrendState.RANGING.value}_{VolatilityState.MEDIUM_VOL.value}_{LiquidityState.LOW_LIQ.value}",
        }
    row = labeled.iloc[-1]
    return {
        "trend_state": str(row["trend_state"]),
        "volatility_state": str(row["volatility_state"]),
        "liquidity_state": str(row["liquidity_state"]),
        "regime_id": str(row["regime_id"]),
    }
