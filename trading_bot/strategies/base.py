"""Abstract strategy: indicators, signal generation, and rejection diagnostics."""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import ClassVar, Optional

import pandas as pd

from trading_bot.core.types import Signal


class BaseStrategy(ABC):
    """Strategy computes indicators and may return a Signal from the last closed bar."""

    REJECTION_CATEGORIES: ClassVar[tuple[str, ...]] = (
        "no_trend_confirmation",
        "rsi_filter",
        "volume_too_low",
        "spread_too_wide",
        "risk_limit",
        "existing_position",
        "range_too_narrow",
        "ema_regime_filter",
        "adx_chop_filter",
        "outside_session_window",
        "invalid_range",
        "timeframe_disabled",
        "no_breakout",
        "regime_blocked",
        "funding_too_expensive",
        "funding_delta_spike",
        "open_interest_spike",
        "adl_risk",
        "liquidation_spike",
        "market_stress",
        "correlation_risk",
        "time_filter",
        "cost_gate",
        "low_liquidity",
        "other",
    )

    def reset_signal_tracking(self) -> None:
        """Reset execution/rejection counters for a new simulation run."""
        self._rejected_signals = {category: 0 for category in self.REJECTION_CATEGORIES}
        self._executed_signals = 0

    @property
    def rejected_signals(self) -> dict[str, int]:
        """Return rejection counters keyed by diagnostic category."""
        if not hasattr(self, "_rejected_signals"):
            self.reset_signal_tracking()
        return dict(self._rejected_signals)

    @property
    def executed_signals(self) -> int:
        """Return the number of signals accepted for simulated execution."""
        if not hasattr(self, "_executed_signals"):
            self.reset_signal_tracking()
        return self._executed_signals

    @property
    def total_signal_outcomes(self) -> int:
        """Return executed plus rejected signal outcomes."""
        return self.executed_signals + sum(self.rejected_signals.values())

    def record_rejection(self, category: str) -> None:
        """Record one rejected signal outcome."""
        if not hasattr(self, "_rejected_signals"):
            self.reset_signal_tracking()
        normalized = category if category in self.REJECTION_CATEGORIES else "other"
        self._rejected_signals[normalized] += 1

    def record_executed_signal(self) -> None:
        """Record one signal accepted for simulated execution."""
        if not hasattr(self, "_executed_signals"):
            self.reset_signal_tracking()
        self._executed_signals += 1

    @abstractmethod
    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add indicator columns to OHLCV DataFrame. No lookahead."""
        pass

    @abstractmethod
    def get_signal(self, df: pd.DataFrame, **kwargs: object) -> Optional[Signal]:
        """
        Return a Signal for the last closed bar (e.g. iloc[-2]) or None.
        kwargs may include: risk_manager (for quantity), config, etc.
        """
        pass
