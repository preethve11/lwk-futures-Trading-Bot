"""Strategies: base interface and implementations."""

from trading_bot.strategies.base import BaseStrategy
from trading_bot.strategies.ema_rsi_vwap import EmaRsiVwapStrategy
from trading_bot.strategies.ema_rsi_vwap_combined import EmaRsiVwapCombinedStrategy
from trading_bot.strategies.ema_rsi_vwap_high_vol import EmaRsiVwapHighVolStrategy
from trading_bot.strategies.ema_rsi_vwap_trend_only import EmaRsiVwapTrendOnlyStrategy
from trading_bot.strategies.session_breakout import SessionBreakoutStrategy

__all__ = [
    "BaseStrategy",
    "EmaRsiVwapCombinedStrategy",
    "EmaRsiVwapHighVolStrategy",
    "EmaRsiVwapStrategy",
    "EmaRsiVwapTrendOnlyStrategy",
    "SessionBreakoutStrategy",
]
