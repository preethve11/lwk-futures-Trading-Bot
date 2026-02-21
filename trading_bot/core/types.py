"""
Core data types for signals, bars, positions, and trades.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class SignalSide(str, Enum):
    LONG = "BUY"
    SHORT = "SELL"


@dataclass
class Bar:
    """OHLCV candle."""
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    @property
    def typical_price(self) -> float:
        return (self.high + self.low + self.close) / 3.0


@dataclass
class Signal:
    """Trading signal with entry, stop, and target."""
    side: SignalSide
    entry_price: float
    stop_price: float
    take_profit_price: float
    quantity: float
    timestamp: datetime
    metadata: dict = field(default_factory=dict)


@dataclass
class Position:
    """Open position state."""
    symbol: str
    side: SignalSide
    quantity: float
    entry_price: float
    unrealized_pnl: float = 0.0
    leverage: int = 1


@dataclass
class Trade:
    """Closed trade for analytics."""
    symbol: str
    side: SignalSide
    quantity: float
    entry_price: float
    exit_price: float
    pnl: float
    pnl_pct: float
    entry_time: datetime
    exit_time: datetime
    exit_reason: str  # "stop_loss" | "take_profit" | "trailing_stop" | "manual" | "signal_reverse"
    fees: float = 0.0
    slippage_usd: float = 0.0
