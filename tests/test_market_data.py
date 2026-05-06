from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json

from app.market_data.binance_ws import BinanceKlineStreamService
from app.market_data.models import KlineEvent
from app.market_data.provider import RedisMarketDataProvider
from app.market_data.redis_store import RedisKlineStore


def _binance_message(symbol: str = "ZECUSDT", *, open_time: int = 1_767_225_600_000) -> dict[str, object]:
    return {
        "stream": f"{symbol.lower()}@kline_5m",
        "data": {
            "E": open_time + 1_000,
            "k": {
                "t": open_time,
                "T": open_time + 299_999,
                "s": symbol,
                "i": "5m",
                "o": "100.0",
                "h": "103.0",
                "l": "99.0",
                "c": "101.0",
                "v": "42.5",
                "x": True,
            },
        },
    }


class FakeAsyncRedis:
    def __init__(self) -> None:
        self.lists: dict[str, list[str]] = {}
        self.values: dict[str, str] = {}
        self.published: list[tuple[str, str]] = []

    async def publish(self, channel: str, message: str) -> object:
        self.published.append((channel, message))
        return 1

    async def set(self, name: str, value: str) -> object:
        self.values[name] = value
        return True

    async def lpush(self, name: str, *values: str) -> object:
        self.lists.setdefault(name, [])
        self.lists[name] = list(values) + self.lists[name]
        return len(self.lists[name])

    async def ltrim(self, name: str, start: int, end: int) -> object:
        self.lists[name] = self.lists.get(name, [])[start : end + 1]
        return True


class FakeSyncRedis:
    def __init__(self, items: list[str], values: dict[str, str] | None = None) -> None:
        self.items = items
        self.values = values or {}

    def get(self, name: str) -> bytes | str | None:
        return self.values.get(name)

    def lrange(self, name: str, start: int, end: int) -> list[bytes | str]:
        return self.items[start : end + 1]


class FakeWebSocket:
    def __init__(self, messages: list[str]) -> None:
        self.messages = messages
        self.index = 0

    async def __aenter__(self) -> FakeWebSocket:
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    def __aiter__(self) -> FakeWebSocket:
        return self

    async def __anext__(self) -> str:
        if self.index >= len(self.messages):
            raise StopAsyncIteration
        message = self.messages[self.index]
        self.index += 1
        return message


def test_kline_event_normalizes_binance_payload() -> None:
    event = KlineEvent.from_binance_message(_binance_message())

    assert event.symbol == "ZECUSDT"
    assert event.interval == "5m"
    assert event.open == 100.0
    assert event.high == 103.0
    assert event.low == 99.0
    assert event.close == 101.0
    assert event.volume == 42.5
    assert event.is_closed is True
    assert event.open_time.tzinfo == timezone.utc


def test_redis_store_publishes_channels_and_loads_dataframe() -> None:
    async_redis = FakeAsyncRedis()
    store = RedisKlineStore(history_size=2)
    event = KlineEvent.from_binance_message(_binance_message())

    asyncio.run(store.publish_event(async_redis, event, base_channel="market_data.kline"))
    payload = async_redis.lists["market_data:klines:ZECUSDT:5m"][0]
    dataframe = RedisKlineStore(FakeSyncRedis([payload])).load_dataframe("ZECUSDT", "5m", limit=1)

    assert [channel for channel, _ in async_redis.published] == ["market_data.kline", "market_data.kline.ZECUSDT.5m"]
    assert dataframe.iloc[0]["close"] == 101.0
    assert list(dataframe.columns) == ["time", "open", "high", "low", "close", "volume"]


def test_redis_store_keeps_partial_candle_out_of_closed_history() -> None:
    async_redis = FakeAsyncRedis()
    store = RedisKlineStore(history_size=2)
    closed_event = KlineEvent.from_binance_message(_binance_message())
    partial_event = KlineEvent.from_binance_message(_binance_message(open_time=1_767_225_900_000))
    partial_payload = partial_event.to_payload()
    partial_payload["is_closed"] = False
    partial_event = KlineEvent.from_payload(partial_payload)

    asyncio.run(store.publish_event(async_redis, closed_event))
    asyncio.run(store.publish_event(async_redis, partial_event))
    dataframe = RedisKlineStore(
        FakeSyncRedis(
            async_redis.lists["market_data:klines:ZECUSDT:5m"],
            async_redis.values,
        )
    ).load_dataframe("ZECUSDT", "5m", limit=10)

    assert len(async_redis.lists["market_data:klines:ZECUSDT:5m"]) == 1
    assert dataframe["time"].is_unique
    assert dataframe.iloc[-1]["time"] == partial_event.open_time


def test_binance_stream_service_publishes_websocket_kline() -> None:
    async_redis = FakeAsyncRedis()
    store = RedisKlineStore(history_size=10)
    raw_message = json.dumps(_binance_message())

    service = BinanceKlineStreamService(
        symbols=["ZECUSDT"],
        interval="5m",
        redis_client=async_redis,
        store=store,
        websocket_factory=lambda url: FakeWebSocket([raw_message]),
    )

    published = asyncio.run(service.run(max_messages=1))

    assert published == 1
    assert service.stream_url.endswith("streams=zecusdt@kline_5m")
    assert "market_data:klines:ZECUSDT:5m" in async_redis.lists


def test_binance_stream_service_zero_message_smoke_does_not_connect() -> None:
    async_redis = FakeAsyncRedis()
    service = BinanceKlineStreamService(
        symbols=["ZECUSDT"],
        interval="5m",
        redis_client=async_redis,
        store=RedisKlineStore(history_size=10),
        websocket_factory=lambda url: FakeWebSocket([json.dumps(_binance_message())]),
    )

    published = asyncio.run(service.run(max_messages=0))

    assert published == 0
    assert async_redis.published == []


def test_redis_market_data_provider_feeds_strategy_dataframe() -> None:
    event = KlineEvent(
        symbol="BTCUSDT",
        interval="1m",
        open_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        close_time=datetime(2026, 1, 1, 0, 0, 59, tzinfo=timezone.utc),
        open=10.0,
        high=12.0,
        low=9.0,
        close=11.0,
        volume=5.0,
        is_closed=True,
        event_time=datetime(2026, 1, 1, 0, 0, 59, tzinfo=timezone.utc),
    )
    store = RedisKlineStore(FakeSyncRedis([json.dumps(event.to_payload())]))
    provider = RedisMarketDataProvider(store)

    dataframe = provider.get_klines("BTCUSDT", "1m")

    assert dataframe.iloc[0]["close"] == 11.0
