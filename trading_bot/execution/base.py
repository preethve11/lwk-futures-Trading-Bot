"""Abstract execution interface: market data and order placement."""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, List, Optional

import pandas as pd

from trading_bot.core.types import Signal, Position


@dataclass
class OrderResult:
    """Result of placing an order (or batch)."""
    success: bool
    order_id: Optional[str] = None
    avg_price: Optional[float] = None
    quantity: Optional[float] = None
    message: str = ""


class ExecutionClient(ABC):
    """Abstract client: klines, symbol info, position, place order with SL/TP."""

    @abstractmethod
    def get_klines(self, symbol: str, interval: str, limit: int = 300) -> pd.DataFrame:
        """Return OHLCV DataFrame with columns: time, open, high, low, close, volume."""
        pass

    @abstractmethod
    def get_symbol_info(self, symbol: str) -> Optional[dict]:
        """Exchange symbol info (filters, etc.)."""
        pass

    @abstractmethod
    def get_open_position(self, symbol: str) -> Optional[Position]:
        """Current open position for symbol, or None."""
        pass

    @abstractmethod
    def place_market_and_sl_tp(
        self,
        symbol: str,
        signal: Signal,
    ) -> OrderResult:
        """Place market order and attach SL + TP (reduce-only). Return fill price and success."""
        pass

    @abstractmethod
    def set_leverage(self, symbol: str, leverage: int) -> None:
        """Set leverage for symbol."""
        pass

    def fetch_recent_trades(self, symbol: str, limit: int = 100) -> List[dict]:
        """Optional: recent trades for PnL reconciliation. Default empty."""
        return []
