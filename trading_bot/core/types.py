"""
Core data types for signals, bars, positions, and trades.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


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
    metadata: dict[str, object] = field(default_factory=dict)


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
    intended_stop_loss: float = 0.0
    intended_take_profit: float = 0.0
    exit_slippage: float = 0.0
    premature_stop: bool = False
    target_approach_pct: float = 0.0
    volatility_regime: str = ""
    trend_regime: str = ""
    volume_regime: str = ""
    signal_rejected_reason: str = ""
    range_width_pct: float = 0.0
    ema_50: float = 0.0
    adx_14: float = 0.0
    intended_sl_pct: float = 0.0
    intended_tp_pct: float = 0.0
    session_name: str = ""
    session_open_time_utc: str = ""
