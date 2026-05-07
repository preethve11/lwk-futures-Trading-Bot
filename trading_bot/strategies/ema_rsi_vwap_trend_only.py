"""EMA/RSI/VWAP variant that only trades in ADX-confirmed trends."""

from __future__ import annotations

import pandas as pd

from trading_bot.analytics.regime import TrendRegime, add_regime_labels
from trading_bot.core.types import Signal
from trading_bot.strategies.ema_rsi_vwap import EmaRsiVwapStrategy


class EmaRsiVwapTrendOnlyStrategy(EmaRsiVwapStrategy):
    """Trade the base strategy only when the latest closed bar is TRENDING."""

    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add base indicators and regime labels."""
        return add_regime_labels(super().compute_indicators(df))

    def get_signal(self, df: pd.DataFrame, **kwargs: object) -> Signal | None:
        """Reject otherwise valid signals outside TRENDING regime."""
        signal = super().get_signal(df, **kwargs)
        if signal is None:
            return None
        regime = str(df.iloc[-2].get("trend_regime", ""))
        if regime != TrendRegime.TRENDING.value:
            self.record_rejection("no_trend_confirmation")
            return None
        signal.metadata["trend_regime"] = regime
        return signal
