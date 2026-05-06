"""Binance USDT-M futures kline WebSocket publisher."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from inspect import isawaitable
import json
import logging
from typing import Any

from app.market_data.models import KlineEvent
from app.market_data.redis_store import AsyncRedisClient, RedisKlineStore

logger = logging.getLogger("trading_bot.market_data.binance_ws")

WebSocketFactory = Callable[[str], AbstractAsyncContextManager[Any]]
SleepFn = Callable[[float], object]


class BinanceKlineStreamService:
    """Subscribe to Binance kline streams and publish normalized events to Redis."""

    LIVE_BASE_URL = "wss://fstream.binance.com/stream"
    TESTNET_BASE_URL = "wss://stream.binancefuture.com/stream"

    def __init__(
        self,
        *,
        symbols: list[str],
        interval: str,
        redis_client: AsyncRedisClient,
        store: RedisKlineStore,
        testnet: bool = True,
        base_channel: str = "market_data.kline",
        reconnect_backoff_seconds: float = 2.0,
        websocket_factory: WebSocketFactory | None = None,
        sleep_fn: SleepFn = asyncio.sleep,
    ) -> None:
        if not symbols:
            raise ValueError("At least one symbol is required")
        self.symbols = [symbol.strip().upper() for symbol in symbols if symbol.strip()]
        if not self.symbols:
            raise ValueError("At least one non-empty symbol is required")
        self.interval = interval
        self.redis_client = redis_client
        self.store = store
        self.testnet = testnet
        self.base_channel = base_channel
        self.reconnect_backoff_seconds = reconnect_backoff_seconds
        self.websocket_factory = websocket_factory or _websocket_connect
        self.sleep_fn = sleep_fn
        self._stop_event = asyncio.Event()

    @property
    def stream_url(self) -> str:
        streams = "/".join(f"{symbol.lower()}@kline_{self.interval}" for symbol in self.symbols)
        base_url = self.TESTNET_BASE_URL if self.testnet else self.LIVE_BASE_URL
        return f"{base_url}?streams={streams}"

    def stop(self) -> None:
        """Request graceful shutdown after the current message or reconnect sleep."""
        self._stop_event.set()

    async def run(self, *, max_messages: int | None = None) -> int:
        """Run until stopped, or until max_messages have been published."""
        if max_messages is not None and max_messages <= 0:
            return 0
        published = 0
        while not self._stop_event.is_set():
            try:
                async with self.websocket_factory(self.stream_url) as websocket:
                    async for raw_message in websocket:
                        event = self.parse_message(raw_message)
                        await self.store.publish_event(self.redis_client, event, base_channel=self.base_channel)
                        published += 1
                        logger.info(
                            "Published kline event",
                            extra={
                                "symbol": event.symbol,
                                "interval": event.interval,
                                "is_closed": event.is_closed,
                                "published": published,
                            },
                        )
                        if max_messages is not None and published >= max_messages:
                            return published
                        if self._stop_event.is_set():
                            return published
            except asyncio.CancelledError:
                self._stop_event.set()
                raise
            except Exception as exc:
                logger.exception(
                    "Kline WebSocket stream failed; reconnecting",
                    extra={"error": str(exc), "url": self.stream_url},
                )
                if self._stop_event.is_set():
                    break
                sleep_result = self.sleep_fn(self.reconnect_backoff_seconds)
                if isawaitable(sleep_result):
                    await sleep_result
        return published

    def parse_message(self, raw_message: str | bytes) -> KlineEvent:
        """Parse a raw WebSocket message into a normalized kline event."""
        raw = raw_message.decode("utf-8") if isinstance(raw_message, bytes) else raw_message
        message = json.loads(raw)
        if not isinstance(message, dict):
            raise ValueError("WebSocket kline message must decode to an object")
        return KlineEvent.from_binance_message(message)


def _websocket_connect(url: str) -> AbstractAsyncContextManager[Any]:
    import websockets

    return websockets.connect(url)
