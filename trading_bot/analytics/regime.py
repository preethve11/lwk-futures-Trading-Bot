"""Market regime detection for strategy research and filtered variants."""

from __future__ import annotations

from enum import Enum

import numpy as np
import pandas as pd


class VolatilityRegime(str, Enum):
    """Rolling volatility regime labels."""

    LOW_VOL = "LOW_VOL"
    MEDIUM_VOL = "MEDIUM_VOL"
    HIGH_VOL = "HIGH_VOL"


class TrendRegime(str, Enum):
    """ADX-based trend regime labels."""

    TRENDING = "TRENDING"
    RANGING = "RANGING"


class VolumeRegime(str, Enum):
    """Rolling volume regime labels."""

    HIGH_VOLUME = "HIGH_VOLUME"
    LOW_VOLUME = "LOW_VOLUME"


def detect_volatility_regime(candles: pd.DataFrame, *, window: int = 50) -> pd.Series:
    """Classify LOW/MEDIUM/HIGH volatility from rolling close-return standard deviation."""
    returns = candles["close"].astype(float).pct_change()
    rolling_vol = returns.rolling(window=window, min_periods=max(5, min(window, 10))).std()
    low_threshold = rolling_vol.quantile(0.33)
    high_threshold = rolling_vol.quantile(0.66)
    labels = np.select(
        [rolling_vol <= low_threshold, rolling_vol >= high_threshold],
        [VolatilityRegime.LOW_VOL.value, VolatilityRegime.HIGH_VOL.value],
        default=VolatilityRegime.MEDIUM_VOL.value,
    )
    return pd.Series(labels, index=candles.index, name="volatility_regime").fillna(VolatilityRegime.MEDIUM_VOL.value)


def calculate_adx(candles: pd.DataFrame, *, window: int = 14) -> pd.Series:
    """Calculate Average Directional Index from OHLC candles."""
    high = candles["high"].astype(float)
    low = candles["low"].astype(float)
    close = candles["close"].astype(float)

    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=candles.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=candles.index)

    true_range = pd.concat(
        [
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = true_range.rolling(window=window, min_periods=window).mean()
    plus_di = 100.0 * plus_dm.rolling(window=window, min_periods=window).mean() / atr.replace(0, np.nan)
    minus_di = 100.0 * minus_dm.rolling(window=window, min_periods=window).mean() / atr.replace(0, np.nan)
    dx = ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)) * 100.0
    return dx.rolling(window=window, min_periods=window).mean().fillna(0.0).rename("adx")


def detect_trend_regime(candles: pd.DataFrame, *, adx_window: int = 14, threshold: float = 25.0) -> pd.Series:
    """Classify TRENDING/RANGING using ADX threshold."""
    adx = calculate_adx(candles, window=adx_window)
    labels = np.where(adx > threshold, TrendRegime.TRENDING.value, TrendRegime.RANGING.value)
    return pd.Series(labels, index=candles.index, name="trend_regime")


def detect_volume_regime(candles: pd.DataFrame, *, window: int = 20) -> pd.Series:
    """Classify HIGH/LOW volume from current volume versus rolling volume average."""
    volume = candles["volume"].astype(float)
    volume_ma = volume.rolling(window=window, min_periods=max(3, min(window, 5))).mean()
    labels = np.where(volume >= volume_ma, VolumeRegime.HIGH_VOLUME.value, VolumeRegime.LOW_VOLUME.value)
    return pd.Series(labels, index=candles.index, name="volume_regime")


def add_regime_labels(candles: pd.DataFrame) -> pd.DataFrame:
    """Return candles with volatility, trend, volume, and ADX regime columns."""
    enriched = candles.copy()
    enriched["adx"] = calculate_adx(enriched)
    enriched["volatility_regime"] = detect_volatility_regime(enriched)
    enriched["trend_regime"] = np.where(enriched["adx"] > 25.0, TrendRegime.TRENDING.value, TrendRegime.RANGING.value)
    enriched["volume_regime"] = detect_volume_regime(enriched)
    return enriched
