"""CCXT-based Binance OHLCV downloader."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol, cast

import pandas as pd

from trading_bot.data.market_data import MarketDataQualityReport, clean_ohlcv


class CCXTExchange(Protocol):
    """Small CCXT surface needed for OHLCV downloads."""

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1m",
        since: int | None = None,
        limit: int | None = None,
        params: dict[str, object] | None = None,
    ) -> list[list[object]]:
        """Fetch OHLCV rows from an exchange."""
        ...


@dataclass(frozen=True)
class OHLCVDownloadResult:
    """Downloaded and cleaned OHLCV data plus quality diagnostics."""

    candles: pd.DataFrame
    quality: MarketDataQualityReport


class BinanceCCXTOHLCVDownloader:
    """Download Binance OHLCV using CCXT with optional testnet URLs."""

    def __init__(self, exchange: CCXTExchange | None = None, *, testnet: bool = True) -> None:
        self.exchange = exchange or _create_binance_exchange(testnet=testnet)

    def download(
        self,
        *,
        symbol: str,
        timeframe: str,
        since: datetime | None = None,
        limit: int = 500,
    ) -> OHLCVDownloadResult:
        """Fetch and normalize OHLCV candles."""
        since_ms = int(since.replace(tzinfo=timezone.utc).timestamp() * 1000) if since is not None else None
        raw_rows = self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since_ms, limit=limit)
        frame = pd.DataFrame(raw_rows, columns=["time", "open", "high", "low", "close", "volume"])
        if not frame.empty:
            frame["time"] = pd.to_datetime(frame["time"], unit="ms", utc=True)
        candles, quality = clean_ohlcv(frame, timeframe=timeframe)
        return OHLCVDownloadResult(candles=candles, quality=quality)


def _create_binance_exchange(*, testnet: bool) -> CCXTExchange:
    try:
        import ccxt
    except ImportError as exc:
        raise RuntimeError("CCXT is required for BinanceCCXTOHLCVDownloader. Install requirements.txt first.") from exc
    exchange = ccxt.binanceusdm({"enableRateLimit": True})
    if testnet:
        exchange.set_sandbox_mode(True)
    return cast(CCXTExchange, exchange)


def ccxt_symbol(binance_futures_symbol: str) -> str:
    """Convert BTCUSDT style symbols to CCXT BTC/USDT style symbols."""
    normalized = binance_futures_symbol.strip().upper()
    if "/" in normalized:
        return normalized
    if normalized.endswith("USDT"):
        return f"{normalized[:-4]}/USDT"
    return normalized
