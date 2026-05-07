"""Abstract execution interface: market data and order placement."""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

import pandas as pd

from trading_bot.core.types import Position, Signal, SignalSide


@dataclass
class ProtectedOrderResult:
    """Verified bracket-order protection outcome."""

    entry_order_id: Optional[str] = None
    stop_order_id: Optional[str] = None
    take_profit_order_id: Optional[str] = None
    protected: bool = False
    requires_manual_review: bool = False
    message: str = ""


@dataclass
class OrderResult:
    """Result of placing an order (or batch)."""
    success: bool
    order_id: Optional[str] = None
    avg_price: Optional[float] = None
    quantity: Optional[float] = None
    message: str = ""
    protected_order: Optional[ProtectedOrderResult] = None


@dataclass(frozen=True)
class ExchangeOrderStatus:
    """Normalized exchange order status for lifecycle reconciliation."""

    order_id: str
    symbol: str
    status: str
    order_type: str = ""
    side: str = ""
    price: Optional[float] = None
    stop_price: Optional[float] = None
    original_quantity: Optional[float] = None
    executed_quantity: Optional[float] = None
    avg_price: Optional[float] = None
    reduce_only: bool = False
    update_time: Optional[datetime] = None
    raw_response: dict[str, object] = field(default_factory=dict)


class ExecutionClient(ABC):
    """Abstract client: klines, symbol info, position, place order with SL/TP."""

    @abstractmethod
    def get_klines(self, symbol: str, interval: str, limit: int = 300) -> pd.DataFrame:
        """Return OHLCV DataFrame with columns: time, open, high, low, close, volume."""
        pass

    @abstractmethod
    def get_symbol_info(self, symbol: str) -> Optional[dict[str, object]]:
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

    @abstractmethod
    def get_open_orders(self, symbol: str) -> List[dict[str, object]]:
        """Return active exchange orders for a symbol."""
        pass

    @abstractmethod
    def emergency_close_position(
        self,
        symbol: str,
        side: SignalSide,
        quantity: float,
    ) -> OrderResult:
        """Close an unprotected position with a reduce-only market order."""
        pass

    def fetch_recent_trades(self, symbol: str, limit: int = 100) -> List[dict[str, object]]:
        """Optional: recent trades for PnL reconciliation. Default empty."""
        return []

    def get_order_status(self, symbol: str, order_id: str) -> ExchangeOrderStatus | None:
        """Optional: return a normalized order status for lifecycle reconciliation."""
        return None

    def cancel_order(self, symbol: str, order_id: str) -> OrderResult:
        """Optional: cancel a single exchange order."""
        return OrderResult(success=False, order_id=order_id, message="cancel_order is not supported")
