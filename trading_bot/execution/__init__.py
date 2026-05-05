"""Execution: exchange abstraction and Binance Futures implementation."""

from trading_bot.execution.base import ExecutionClient, OrderResult, ProtectedOrderResult
from trading_bot.execution.binance_futures import BinanceFuturesClient

__all__ = ["ExecutionClient", "OrderResult", "ProtectedOrderResult", "BinanceFuturesClient"]
