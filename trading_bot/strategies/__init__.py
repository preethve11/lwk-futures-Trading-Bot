"""Strategies: base interface and implementations."""

from trading_bot.strategies.base import BaseStrategy
from trading_bot.strategies.ema_rsi_vwap import EmaRsiVwapStrategy

__all__ = ["BaseStrategy", "EmaRsiVwapStrategy"]
