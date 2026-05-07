from __future__ import annotations

import pandas as pd

from trading_bot.analytics.regime import (
    TrendRegime,
    VolumeRegime,
    VolatilityRegime,
    add_regime_labels,
    detect_trend_regime,
    detect_volume_regime,
    detect_volatility_regime,
)


def _candles(periods: int = 80) -> pd.DataFrame:
    closes = [100.0 + index * 0.4 for index in range(periods)]
    return pd.DataFrame(
        {
            "time": pd.date_range("2026-01-01", periods=periods, freq="15min", tz="UTC"),
            "open": [close - 0.1 for close in closes],
            "high": [close + 0.8 for close in closes],
            "low": [close - 0.8 for close in closes],
            "close": closes,
            "volume": [100.0 + index for index in range(periods)],
        }
    )


def test_regime_detectors_return_expected_labels() -> None:
    candles = _candles()

    volatility = detect_volatility_regime(candles)
    trend = detect_trend_regime(candles)
    volume = detect_volume_regime(candles)

    assert set(volatility.dropna()).issubset({item.value for item in VolatilityRegime})
    assert set(trend.dropna()).issubset({item.value for item in TrendRegime})
    assert set(volume.dropna()).issubset({item.value for item in VolumeRegime})


def test_add_regime_labels_adds_research_columns() -> None:
    enriched = add_regime_labels(_candles())

    assert {"adx", "volatility_regime", "trend_regime", "volume_regime"}.issubset(enriched.columns)
    assert len(enriched) == 80
