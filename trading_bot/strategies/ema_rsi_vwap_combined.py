"""EMA/RSI/VWAP variant that requires trend and high-volume confirmation."""

from __future__ import annotations

import pandas as pd

from trading_bot.analytics.regime import TrendRegime, VolumeRegime, add_regime_labels
from trading_bot.core.types import Signal
from trading_bot.strategies.ema_rsi_vwap import EmaRsiVwapStrategy


class EmaRsiVwapCombinedStrategy(EmaRsiVwapStrategy):
    """Trade the base strategy only when TRENDING and HIGH_VOLUME regimes agree."""

    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add base indicators and regime labels."""
        return add_regime_labels(super().compute_indicators(df))

    def get_signal(self, df: pd.DataFrame, **kwargs: object) -> Signal | None:
        """Reject otherwise valid signals outside the combined favorable regime."""
        signal = super().get_signal(df, **kwargs)
        if signal is None:
            return None
        trend = str(df.iloc[-2].get("trend_regime", ""))
        volume = str(df.iloc[-2].get("volume_regime", ""))
        if trend != TrendRegime.TRENDING.value:
            self.record_rejection("no_trend_confirmation")
            return None
        if volume != VolumeRegime.HIGH_VOLUME.value:
            self.record_rejection("volume_too_low")
            return None
        signal.metadata["trend_regime"] = trend
        signal.metadata["volume_regime"] = volume
        return signal
