"""Strategy-facing market data providers."""

from __future__ import annotations

from typing import Protocol

import pandas as pd

from app.market_data.redis_store import RedisKlineStore


class MarketDataProvider(Protocol):
    def get_klines(self, symbol: str, interval: str, limit: int = 300) -> pd.DataFrame:
        """Return OHLCV data for strategy evaluation."""


class RedisMarketDataProvider:
    """Load strategy klines from Redis instead of REST polling."""

    def __init__(self, store: RedisKlineStore) -> None:
        self.store = store

    @classmethod
    def from_url(cls, redis_url: str, *, history_size: int = 500) -> RedisMarketDataProvider:
        return cls(RedisKlineStore(redis_url=redis_url, history_size=history_size))

    def get_klines(self, symbol: str, interval: str, limit: int = 300) -> pd.DataFrame:
        return self.store.load_dataframe(symbol, interval, limit=limit)
