"""Abstract strategy: indicators + signal generation."""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Optional

import pandas as pd

from trading_bot.core.types import Signal


class BaseStrategy(ABC):
    """Strategy computes indicators and may return a Signal from the last closed bar."""

    @abstractmethod
    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add indicator columns to OHLCV DataFrame. No lookahead."""
        pass

    @abstractmethod
    def get_signal(self, df: pd.DataFrame, **kwargs) -> Optional[Signal]:
        """
        Return a Signal for the last closed bar (e.g. iloc[-2]) or None.
        kwargs may include: risk_manager (for quantity), config, etc.
        """
        pass
