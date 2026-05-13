"""
Binance Futures execution with retry and rate-limit handling.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional, cast

import pandas as pd

from binance.client import Client
from binance.exceptions import BinanceAPIException

from trading_bot.core.types import Position, Signal, SignalSide
from trading_bot.execution.base import (
    AccountSnapshot,
    ExchangeOrderStatus,
    ExecutionClient,
    OrderResult,
    ProtectedOrderResult,
)
from trading_bot.utils.exchange_filters import round_price, parse_symbol_filters

logger = logging.getLogger("trading_bot.execution.binance")


def retry_on_rate_limit(max_retries: int = 3, base_delay: float = 1.0) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator: retry on 429 or 418 (rate limit)."""
    def decorator(f: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(f)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            last_exc: BaseException | None = None
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
            if last_exc is not None:
                raise last_exc
            raise RuntimeError("rate-limit retry exhausted without an exception")
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
            self._client.API_URL = self._client.FUTURES_TESTNET_URL
            self._client.FUTURES_URL = self._client.FUTURES_TESTNET_URL
            self._client.FUTURES_DATA_URL = self._client.FUTURES_DATA_TESTNET_URL
            logger.info("Binance Futures: using TESTNET")
        else:
            logger.info("Binance Futures: using LIVE")
        self._symbol_info_cache: dict[str, dict[str, object]] = {}

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
    def get_symbol_info(self, symbol: str, *, force_refresh: bool = False) -> Optional[dict[str, object]]:
        if not force_refresh and symbol in self._symbol_info_cache:
            return self._symbol_info_cache[symbol]
        info = cast(dict[str, object], self._client.futures_exchange_info())
        symbols = info.get("symbols", [])
        if not isinstance(symbols, list):
            return None
        for item in symbols:
            if isinstance(item, dict) and item.get("symbol") == symbol:
                parsed = dict(item)
                self._symbol_info_cache[symbol] = parsed
                return parsed
        return None

    def refresh_symbol_info(self, symbol: str) -> Optional[dict[str, object]]:
        """Force refresh cached symbol filters after an exchange-side error."""
        return cast(Optional[dict[str, object]], self.get_symbol_info(symbol, force_refresh=True))

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
            entry_order_id = str(res.get("orderId"))
            close_side = "SELL" if side == "BUY" else "BUY"
            tp_order_id = None
            stop_order_id = None
            protection_errors: list[str] = []

            try:
                tp_res = self._client.futures_create_order(
                    symbol=symbol, side=close_side, type="LIMIT", timeInForce="GTC",
                    quantity=str(qty), price=str(tp_r), reduceOnly=True
                )
                tp_order_id = str(tp_res.get("orderId"))
            except BinanceAPIException as e:
                protection_errors.append(f"take-profit placement failed: {e}")

            try:
                stop_res = self._client.futures_create_order(
                    symbol=symbol, side=close_side, type="STOP_MARKET",
                    stopPrice=str(stop_r), quantity=str(qty), reduceOnly=True
                )
                stop_order_id = str(stop_res.get("orderId"))
            except BinanceAPIException as e:
                protection_errors.append(f"stop-loss placement failed: {e}")

            protected = tp_order_id is not None and stop_order_id is not None
            message = "; ".join(protection_errors) if protection_errors else "entry, stop, and take-profit placed"
            if protection_errors:
                self.refresh_symbol_info(symbol)
                logger.critical(
                    "Entry placed but protection order placement failed",
                    extra={"symbol": symbol, "errors": protection_errors},
                )
            return OrderResult(
                success=True,
                order_id=entry_order_id,
                avg_price=avg,
                quantity=qty,
                message=message,
                protected_order=ProtectedOrderResult(
                    entry_order_id=entry_order_id,
                    stop_order_id=stop_order_id,
                    take_profit_order_id=tp_order_id,
                    protected=protected,
                    requires_manual_review=not protected,
                    message=message,
                ),
            )
        except BinanceAPIException as e:
            self.refresh_symbol_info(symbol)
            logger.exception("Binance order error: %s", e)
            return OrderResult(success=False, message=str(e))

    @retry_on_rate_limit(max_retries=2)
    def get_open_orders(self, symbol: str) -> list[dict[str, object]]:
        raw = self._client.futures_get_open_orders(symbol=symbol)
        if not isinstance(raw, list):
            return []
        return [dict(item) for item in raw if isinstance(item, dict)]

    @retry_on_rate_limit(max_retries=2)
    def emergency_close_position(self, symbol: str, side: SignalSide, quantity: float) -> OrderResult:
        close_side = "SELL" if side == SignalSide.LONG else "BUY"
        try:
            res = self._client.futures_create_order(
                symbol=symbol,
                side=close_side,
                type="MARKET",
                quantity=str(quantity),
                reduceOnly=True,
            )
            return OrderResult(
                success=True,
                order_id=str(res.get("orderId")),
                avg_price=float(res.get("avgPrice") or res.get("price") or 0.0),
                quantity=quantity,
                message="emergency market close submitted",
            )
        except BinanceAPIException as e:
            logger.exception("Emergency close failed: %s", e)
            return OrderResult(success=False, quantity=quantity, message=str(e))

    def fetch_recent_trades(self, symbol: str, limit: int = 100) -> list[dict[str, object]]:
        try:
            raw = self._client.futures_account_trades(symbol=symbol, limit=limit)
            if not isinstance(raw, list):
                return []
            return [dict(item) for item in raw if isinstance(item, dict)]
        except Exception as e:
            logger.exception("fetch_recent_trades: %s", e)
            return []

    @retry_on_rate_limit(max_retries=2)
    def fetch_funding_rates(self, symbol: str, limit: int = 100) -> list[dict[str, object]]:
        """Return Binance USD-M funding-rate history rows for a symbol."""
        raw = self._client.futures_funding_rate(symbol=symbol, limit=limit)
        if not isinstance(raw, list):
            return []
        return [dict(item) for item in raw if isinstance(item, dict)]

    @retry_on_rate_limit(max_retries=2)
    def fetch_open_interest(self, symbol: str) -> dict[str, object]:
        """Return the current Binance USD-M open-interest snapshot."""
        raw = self._client.futures_open_interest(symbol=symbol)
        return dict(raw) if isinstance(raw, dict) else {}

    @retry_on_rate_limit(max_retries=2)
    def fetch_open_interest_history(self, symbol: str, *, period: str = "1h", limit: int = 100) -> list[dict[str, object]]:
        """Return historical open-interest statistics for crowding detection."""
        raw = self._client.futures_open_interest_hist(symbol=symbol, period=period, limit=limit)
        if not isinstance(raw, list):
            return []
        return [dict(item) for item in raw if isinstance(item, dict)]

    @retry_on_rate_limit(max_retries=2)
    def fetch_adl_quantile(self, symbol: str | None = None) -> list[dict[str, object]]:
        """Return position ADL quantile estimation rows for the account."""
        kwargs = {"symbol": symbol} if symbol is not None else {}
        raw = self._client.futures_adl_quantile_estimate(**kwargs)
        if not isinstance(raw, list):
            return []
        return [dict(item) for item in raw if isinstance(item, dict)]

    @retry_on_rate_limit(max_retries=2)
    def fetch_force_orders(self, symbol: str, limit: int = 100) -> list[dict[str, object]]:
        """Return user force-order/liquidation records when the account has any."""
        raw = self._client.futures_liquidation_orders(symbol=symbol, limit=limit)
        if not isinstance(raw, list):
            return []
        return [dict(item) for item in raw if isinstance(item, dict)]

    @retry_on_rate_limit(max_retries=2)
    def get_order_status(self, symbol: str, order_id: str) -> ExchangeOrderStatus | None:
        try:
            raw = self._client.futures_get_order(symbol=symbol, orderId=order_id)
        except BinanceAPIException as e:
            logger.exception("Could not fetch Binance order status: %s", e)
            return None
        return ExchangeOrderStatus(
            order_id=str(raw.get("orderId") or order_id),
            symbol=str(raw.get("symbol") or symbol),
            status=str(raw.get("status") or "").upper(),
            order_type=str(raw.get("type") or raw.get("origType") or "").upper(),
            side=str(raw.get("side") or "").upper(),
            price=_float_or_none(raw.get("price")),
            stop_price=_float_or_none(raw.get("stopPrice")),
            original_quantity=_float_or_none(raw.get("origQty")),
            executed_quantity=_float_or_none(raw.get("executedQty")),
            avg_price=_float_or_none(raw.get("avgPrice")),
            reduce_only=_bool_value(raw.get("reduceOnly")),
            update_time=_datetime_from_millis(raw.get("updateTime")),
            raw_response=dict(raw),
        )

    @retry_on_rate_limit(max_retries=2)
    def cancel_order(self, symbol: str, order_id: str) -> OrderResult:
        try:
            raw = self._client.futures_cancel_order(symbol=symbol, orderId=order_id)
            return OrderResult(
                success=True,
                order_id=str(raw.get("orderId") or order_id),
                message=str(raw.get("status") or "cancel submitted"),
            )
        except BinanceAPIException as e:
            logger.exception("Could not cancel Binance order: %s", e)
            return OrderResult(success=False, order_id=order_id, message=str(e))

    @retry_on_rate_limit(max_retries=2)
    def get_account_snapshot(self, asset: str = "USDT") -> AccountSnapshot | None:
        try:
            raw = self._client.futures_account()
        except BinanceAPIException as e:
            logger.exception("Could not fetch Binance account snapshot: %s", e)
            return None
        selected_asset = _find_account_asset(raw, asset)
        wallet_balance = _first_float(
            raw.get("totalWalletBalance"),
            selected_asset.get("walletBalance") if selected_asset is not None else None,
        )
        unrealized_pnl = _first_float(
            raw.get("totalUnrealizedProfit"),
            selected_asset.get("unrealizedProfit") if selected_asset is not None else None,
        )
        margin_balance = _first_float(
            raw.get("totalMarginBalance"),
            selected_asset.get("marginBalance") if selected_asset is not None else None,
            wallet_balance + unrealized_pnl,
        )
        available_balance = _first_float(
            raw.get("availableBalance"),
            selected_asset.get("availableBalance") if selected_asset is not None else None,
        )
        max_withdraw_amount = _first_optional_float(
            raw.get("maxWithdrawAmount"),
            selected_asset.get("maxWithdrawAmount") if selected_asset is not None else None,
        )
        event_time = _datetime_from_millis(raw.get("updateTime"))
        if event_time is None and selected_asset is not None:
            event_time = _datetime_from_millis(selected_asset.get("updateTime"))
        return AccountSnapshot(
            asset=asset.upper(),
            wallet_balance=wallet_balance,
            unrealized_pnl=unrealized_pnl,
            margin_balance=margin_balance,
            available_balance=available_balance,
            max_withdraw_amount=max_withdraw_amount,
            event_time=event_time,
            raw_response=dict(raw),
        )


def _float_or_none(value: object) -> float | None:
    if value is None or value == "":
        return None
    if not isinstance(value, (str, bytes, bytearray, int, float)):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed


def _first_float(*values: object) -> float:
    for value in values:
        parsed = _float_or_none(value)
        if parsed is not None:
            return parsed
    return 0.0


def _first_optional_float(*values: object) -> float | None:
    for value in values:
        parsed = _float_or_none(value)
        if parsed is not None:
            return parsed
    return None


def _find_account_asset(raw: dict[str, object], asset: str) -> dict[str, object] | None:
    requested = asset.upper()
    assets = raw.get("assets")
    if not isinstance(assets, list):
        return None
    for item in assets:
        if isinstance(item, dict) and str(item.get("asset") or "").upper() == requested:
            return dict(item)
    return None


def _bool_value(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() == "true"
    if isinstance(value, int):
        return value != 0
    return False


def _datetime_from_millis(value: object) -> datetime | None:
    if not isinstance(value, (str, bytes, bytearray, int, float)):
        return None
    try:
        millis = int(value)
    except (TypeError, ValueError):
        return None
    if millis <= 0:
        return None
    return datetime.fromtimestamp(millis / 1000.0, tz=timezone.utc)
