"""
Binance Futures execution with retry and rate-limit handling.
"""

from __future__ import annotations
import logging
import time
from typing import Optional, List

import pandas as pd

from binance.client import Client
from binance.exceptions import BinanceAPIException

from trading_bot.core.types import Signal, SignalSide, Position, Bar
from trading_bot.execution.base import ExecutionClient, OrderResult
from trading_bot.utils.exchange_filters import round_price, parse_symbol_filters

logger = logging.getLogger("trading_bot.execution.binance")


def retry_on_rate_limit(max_retries: int = 3, base_delay: float = 1.0):
    """Decorator: retry on 429 or 418 (rate limit)."""
    def decorator(f):
        def wrapped(*args, **kwargs):
            last_exc = None
            for attempt in range(max_retries):
                try:
                    return f(*args, **kwargs)
                except BinanceAPIException as e:
                    last_exc = e
                    if e.status_code in (429, 418) and attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        logger.warning("Rate limited, retry in %.1fs (attempt %d)", delay, attempt + 1)
                        time.sleep(delay)
                    else:
                        raise
            raise last_exc
        return wrapped
    return decorator


class BinanceFuturesClient(ExecutionClient):
    """Binance USDT-M Futures client (testnet and live)."""

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        testnet: bool = True,
    ):
        self._client = Client(api_key, api_secret)
        if testnet:
            self._client.API_URL = "https://testnet.binancefuture.com/fapi"
            logger.info("Binance Futures: using TESTNET")
        else:
            logger.info("Binance Futures: using LIVE")
        self._symbol_info_cache: Optional[dict] = None

    @retry_on_rate_limit(max_retries=3, base_delay=1.0)
    def get_klines(self, symbol: str, interval: str, limit: int = 300) -> pd.DataFrame:
        raw = self._client.futures_klines(symbol=symbol, interval=interval, limit=limit)
        df = pd.DataFrame(raw, columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_av", "num_trades", "tb_base_av", "tb_quote_av", "ignore"
        ])
        df[["open", "high", "low", "close", "volume"]] = df[["open", "high", "low", "close", "volume"]].astype(float)
        df["time"] = pd.to_datetime(df["open_time"], unit="ms")
        return df[["time", "open", "high", "low", "close", "volume"]]

    @retry_on_rate_limit(max_retries=2)
    def get_symbol_info(self, symbol: str) -> Optional[dict]:
        info = self._client.futures_exchange_info()
        for s in info.get("symbols", []):
            if s.get("symbol") == symbol:
                return s
        return None

    @retry_on_rate_limit(max_retries=2)
    def get_open_position(self, symbol: str) -> Optional[Position]:
        pos_info = self._client.futures_position_information(symbol=symbol)
        for p in pos_info:
            amt = float(p.get("positionAmt", 0.0))
            if amt != 0:
                side = SignalSide.LONG if amt > 0 else SignalSide.SHORT
                return Position(
                    symbol=symbol,
                    side=side,
                    quantity=abs(amt),
                    entry_price=float(p.get("entryPrice", 0)),
                    unrealized_pnl=float(p.get("unRealizedProfit", 0)),
                    leverage=int(p.get("leverage", 1)),
                )
        return None

    def set_leverage(self, symbol: str, leverage: int) -> None:
        try:
            self._client.futures_change_leverage(symbol=symbol, leverage=leverage)
            logger.info("Leverage set to %sx for %s", leverage, symbol)
        except BinanceAPIException as e:
            logger.warning("Could not set leverage: %s", e)

    @retry_on_rate_limit(max_retries=2)
    def place_market_and_sl_tp(self, symbol: str, signal: Signal) -> OrderResult:
        """Place market order then SL and TP (reduce-only)."""
        qty = signal.quantity
        side = signal.side.value
        stop = signal.stop_price
        tp = signal.take_profit_price
        _, _, price_tick = parse_symbol_filters(self.get_symbol_info(symbol))
        stop_r = round_price(stop, price_tick)
        tp_r = round_price(tp, price_tick)
        try:
            res = self._client.futures_create_order(
                symbol=symbol, side=side, type="MARKET", quantity=str(qty)
            )
            avg = float(res.get("avgPrice") or res.get("price") or signal.entry_price)
            # SL and TP
            close_side = "SELL" if side == "BUY" else "BUY"
            self._client.futures_create_order(
                symbol=symbol, side=close_side, type="LIMIT", timeInForce="GTC",
                quantity=str(qty), price=str(tp_r), reduceOnly=True
            )
            self._client.futures_create_order(
                symbol=symbol, side=close_side, type="STOP_MARKET",
                stopPrice=str(stop_r), quantity=str(qty), reduceOnly=True
            )
            return OrderResult(success=True, order_id=str(res.get("orderId")), avg_price=avg, quantity=qty)
        except BinanceAPIException as e:
            logger.exception("Binance order error: %s", e)
            return OrderResult(success=False, message=str(e))

    def fetch_recent_trades(self, symbol: str, limit: int = 100) -> List[dict]:
        try:
            return self._client.futures_account_trades(symbol=symbol, limit=limit)
        except Exception as e:
            logger.exception("fetch_recent_trades: %s", e)
            return []
