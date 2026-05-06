"""Normalized exchange fill parsing helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from collections.abc import Mapping


@dataclass(frozen=True)
class ExchangeFill:
    """A normalized execution fill from Binance account trades."""

    symbol: str
    exchange_trade_id: str
    exchange_order_id: str
    side: str
    position_side: str
    price: float
    quantity: float
    quote_quantity: float
    realized_pnl: float
    commission: float
    commission_asset: str
    buyer: bool
    maker: bool
    event_time: datetime
    raw_payload: dict[str, object]

    @property
    def is_closing_fill(self) -> bool:
        """Return true when Binance reported realized PnL for this fill."""
        return abs(self.realized_pnl) > 1e-12

    @property
    def inferred_position_side(self) -> str:
        """Infer the original position side closed by this fill."""
        return "BUY" if self.side == "SELL" else "SELL"

    @property
    def inferred_entry_price(self) -> float:
        """Infer entry price from realized PnL for a one-way USDT-M futures fill."""
        if self.quantity <= 0:
            return self.price
        pnl_per_unit = self.realized_pnl / self.quantity
        if self.side == "SELL":
            return max(0.0, self.price - pnl_per_unit)
        return max(0.0, self.price + pnl_per_unit)

    @property
    def inferred_pnl_pct(self) -> float:
        """Infer PnL percent from the reconstructed entry notional."""
        notional = self.inferred_entry_price * self.quantity
        if notional <= 0:
            return 0.0
        return (self.realized_pnl / notional) * 100.0


def parse_exchange_fill(payload: Mapping[str, object], *, fallback_symbol: str) -> ExchangeFill:
    """Parse a Binance account-trade payload into a normalized exchange fill."""
    raw_payload = dict(payload)
    symbol = _string_value(payload, "symbol", fallback_symbol).upper()
    side = _string_value(payload, "side", "").upper()
    if side not in {"BUY", "SELL"}:
        raise ValueError(f"Unsupported exchange fill side for {symbol}: {side!r}")

    exchange_trade_id = _string_value(payload, "id") or _string_value(payload, "tradeId")
    if not exchange_trade_id:
        exchange_trade_id = _stable_fill_id(symbol, payload)

    return ExchangeFill(
        symbol=symbol,
        exchange_trade_id=exchange_trade_id,
        exchange_order_id=_string_value(payload, "orderId"),
        side=side,
        position_side=_string_value(payload, "positionSide"),
        price=_float_value(payload, "price"),
        quantity=_float_value(payload, "qty"),
        quote_quantity=_float_value(payload, "quoteQty"),
        realized_pnl=_float_value(payload, "realizedPnl"),
        commission=_float_value(payload, "commission"),
        commission_asset=_string_value(payload, "commissionAsset"),
        buyer=_bool_value(payload, "buyer"),
        maker=_bool_value(payload, "maker"),
        event_time=_datetime_from_millis(payload.get("time")),
        raw_payload=raw_payload,
    )


def _string_value(payload: Mapping[str, object], key: str, default: str = "") -> str:
    value = payload.get(key)
    if value is None:
        return default
    text = str(value)
    return text if text else default


def _float_value(payload: Mapping[str, object], key: str, default: float = 0.0) -> float:
    value = payload.get(key)
    if value is None or value == "":
        return default
    if not isinstance(value, (str, bytes, bytearray, int, float)):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _bool_value(payload: Mapping[str, object], key: str, default: bool = False) -> bool:
    value = payload.get(key)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() == "true"
    if isinstance(value, int):
        return value != 0
    return default


def _datetime_from_millis(value: object) -> datetime:
    if not isinstance(value, (str, bytes, bytearray, int, float)):
        return datetime.now(timezone.utc)
    try:
        millis = int(value)
    except (TypeError, ValueError):
        millis = 0
    if millis <= 0:
        return datetime.now(timezone.utc)
    return datetime.fromtimestamp(millis / 1000.0, tz=timezone.utc)


def _stable_fill_id(symbol: str, payload: Mapping[str, object]) -> str:
    fields = {
        "symbol": symbol,
        "orderId": _string_value(payload, "orderId"),
        "time": _string_value(payload, "time"),
        "side": _string_value(payload, "side"),
        "price": _string_value(payload, "price"),
        "qty": _string_value(payload, "qty"),
        "realizedPnl": _string_value(payload, "realizedPnl"),
    }
    material = json.dumps(fields, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]
    return f"synthetic:{digest}"
