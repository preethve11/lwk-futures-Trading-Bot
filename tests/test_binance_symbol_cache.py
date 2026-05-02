from __future__ import annotations

from trading_bot.execution.binance_futures import BinanceFuturesClient


class _FakeRawClient:
    def __init__(self) -> None:
        self.calls = 0

    def futures_exchange_info(self) -> dict[str, list[dict[str, object]]]:
        self.calls += 1
        return {
            "symbols": [
                {
                    "symbol": "ZECUSDT",
                    "filters": [
                        {"filterType": "LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                        {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
                    ],
                }
            ]
        }


def _client_with_fake_raw_client(raw_client: _FakeRawClient) -> BinanceFuturesClient:
    client = BinanceFuturesClient.__new__(BinanceFuturesClient)
    client._client = raw_client
    client._symbol_info_cache = {}
    return client


def test_symbol_info_is_cached_until_forced_refresh() -> None:
    raw_client = _FakeRawClient()
    client = _client_with_fake_raw_client(raw_client)

    first = client.get_symbol_info("ZECUSDT")
    second = client.get_symbol_info("ZECUSDT")
    refreshed = client.get_symbol_info("ZECUSDT", force_refresh=True)

    assert first == second == refreshed
    assert raw_client.calls == 2
