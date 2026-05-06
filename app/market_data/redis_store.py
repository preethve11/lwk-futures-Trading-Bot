"""Redis storage and pub/sub helpers for kline events."""

from __future__ import annotations

import json
from typing import Any, Protocol, cast

import pandas as pd

from app.market_data.models import KlineEvent, events_to_dataframe


class AsyncRedisClient(Protocol):
    async def publish(self, channel: str, message: str) -> object:
        """Publish a message to a Redis channel."""

    async def set(self, name: str, value: str) -> object:
        """Set a string value."""

    async def lpush(self, name: str, *values: str) -> object:
        """Push values to the front of a Redis list."""

    async def ltrim(self, name: str, start: int, end: int) -> object:
        """Trim a Redis list to a range."""


class SyncRedisClient(Protocol):
    def get(self, name: str) -> bytes | str | None:
        """Read a string value."""

    def lrange(self, name: str, start: int, end: int) -> list[bytes | str]:
        """Read a Redis list range."""


class RedisKlineStore:
    """Reads and writes recent kline history in Redis."""

    def __init__(
        self,
        redis_client: SyncRedisClient | None = None,
        *,
        redis_url: str | None = None,
        history_size: int = 500,
        key_prefix: str = "market_data:klines",
    ) -> None:
        if redis_client is None and redis_url is not None:
            from redis import Redis

            redis_client = cast(SyncRedisClient, Redis.from_url(redis_url))
        self.redis_client = redis_client
        self.history_size = history_size
        self.key_prefix = key_prefix

    @staticmethod
    def channel(base_channel: str, symbol: str, interval: str) -> str:
        return f"{base_channel}.{symbol.upper()}.{interval}"

    def key(self, symbol: str, interval: str) -> str:
        return f"{self.key_prefix}:{symbol.upper()}:{interval}"

    def current_key(self, symbol: str, interval: str) -> str:
        return f"{self.key(symbol, interval)}:current"

    async def publish_event(
        self,
        async_client: AsyncRedisClient,
        event: KlineEvent,
        *,
        base_channel: str = "market_data.kline",
    ) -> None:
        """Persist an event to recent history and publish symbol-specific and aggregate notifications."""
        message = json.dumps(event.to_payload(), separators=(",", ":"))
        await async_client.set(self.current_key(event.symbol, event.interval), message)
        if event.is_closed:
            key = self.key(event.symbol, event.interval)
            await async_client.lpush(key, message)
            await async_client.ltrim(key, 0, self.history_size - 1)
        await async_client.publish(base_channel, message)
        await async_client.publish(self.channel(base_channel, event.symbol, event.interval), message)

    def load_recent_events(self, symbol: str, interval: str, *, limit: int = 300) -> list[KlineEvent]:
        """Load recent kline events from Redis in chronological order."""
        if self.redis_client is None:
            raise RuntimeError("RedisKlineStore has no sync Redis client configured")
        if limit <= 0:
            return []
        raw_items = self.redis_client.lrange(self.key(symbol, interval), 0, max(limit - 1, 0))
        current = self.redis_client.get(self.current_key(symbol, interval))
        if current is not None:
            raw_items.append(current)
        deduped: dict[tuple[str, str, object], KlineEvent] = {}
        for item in raw_items:
            event = KlineEvent.from_payload(_loads(item))
            deduped[(event.symbol, event.interval, event.open_time)] = event
        events = sorted(deduped.values(), key=lambda event: event.open_time)
        return events[-limit:]

    def load_dataframe(self, symbol: str, interval: str, *, limit: int = 300) -> pd.DataFrame:
        """Load recent klines in the DataFrame shape expected by strategies."""
        return events_to_dataframe(self.load_recent_events(symbol, interval, limit=limit))


def _loads(item: bytes | str) -> dict[str, Any]:
    raw = item.decode("utf-8") if isinstance(item, bytes) else item
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("Redis kline item must decode to an object")
    return payload
