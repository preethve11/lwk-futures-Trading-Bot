"""EMA/RSI/VWAP variant that only trades high-volatility regimes."""

from __future__ import annotations

import pandas as pd

from trading_bot.analytics.regime import VolatilityRegime, add_regime_labels
from trading_bot.core.types import Signal
from trading_bot.strategies.ema_rsi_vwap import EmaRsiVwapStrategy


class EmaRsiVwapHighVolStrategy(EmaRsiVwapStrategy):
    """Trade the base strategy only when rolling volatility is HIGH_VOL."""

    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add base indicators and regime labels."""
        return add_regime_labels(super().compute_indicators(df))

    def get_signal(self, df: pd.DataFrame, **kwargs: object) -> Signal | None:
        """Reject otherwise valid signals outside HIGH_VOL regime."""
        signal = super().get_signal(df, **kwargs)
        if signal is None:
            return None
        regime = str(df.iloc[-2].get("volatility_regime", ""))
        if regime != VolatilityRegime.HIGH_VOL.value:
            self.record_rejection("other")
            return None
        signal.metadata["volatility_regime"] = regime
        return signal
