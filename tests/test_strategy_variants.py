from __future__ import annotations

import pandas as pd

from trading_bot.analytics.regime import TrendRegime, VolumeRegime, VolatilityRegime
from trading_bot.strategies.ema_rsi_vwap_combined import EmaRsiVwapCombinedStrategy
from trading_bot.strategies.ema_rsi_vwap_high_vol import EmaRsiVwapHighVolStrategy
from trading_bot.strategies.ema_rsi_vwap_trend_only import EmaRsiVwapTrendOnlyStrategy


def _signal_frame() -> pd.DataFrame:
    rows = []
    for index in range(32):
        close = 100.0 + index
        rows.append(
            {
                "time": pd.Timestamp("2026-01-01T00:00:00Z") + pd.Timedelta(minutes=15 * index),
                "open": close - 0.2,
                "high": close + 0.4,
                "low": close - 0.4,
                "close": close,
                "volume": 1000.0,
                "vwap": close - 2.0,
                "ema_fast": close,
                "ema_slow": close - 1.0,
                "rsi": 60.0,
                "atr": 1.0,
                "vol_ma": 100.0,
                "trend_regime": TrendRegime.TRENDING.value,
                "volatility_regime": VolatilityRegime.HIGH_VOL.value,
                "volume_regime": VolumeRegime.HIGH_VOLUME.value,
            }
        )
    return pd.DataFrame(rows)


def test_trend_only_variant_rejects_ranging_regime() -> None:
    strategy = EmaRsiVwapTrendOnlyStrategy(vol_mult=1.0)
    frame = _signal_frame()
    frame.loc[frame.index[-2], "trend_regime"] = TrendRegime.RANGING.value

    assert strategy.get_signal(frame) is None
    assert strategy.rejected_signals["no_trend_confirmation"] == 1


def test_high_vol_variant_accepts_high_vol_regime() -> None:
    strategy = EmaRsiVwapHighVolStrategy(vol_mult=1.0)

    assert strategy.get_signal(_signal_frame()) is not None


def test_combined_variant_requires_high_volume() -> None:
    strategy = EmaRsiVwapCombinedStrategy(vol_mult=1.0)
    frame = _signal_frame()
    frame.loc[frame.index[-2], "volume_regime"] = VolumeRegime.LOW_VOLUME.value

    assert strategy.get_signal(frame) is None
    assert strategy.rejected_signals["volume_too_low"] == 1
