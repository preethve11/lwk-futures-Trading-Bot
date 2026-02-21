"""Lot size and price filter helpers from exchange info."""

from __future__ import annotations
import math
from typing import Optional


def parse_symbol_filters(symbol_info: Optional[dict]) -> tuple[float, float, float]:
    """
    Extract min_qty, step_size (lot_step), tick_size from symbol filters.
    Returns (min_qty, lot_step, price_tick). Uses defaults if symbol_info is None.
    """
    min_qty = 0.001
    lot_step = 0.0001
    price_tick = 0.01
    if not symbol_info:
        return min_qty, lot_step, price_tick
    for f in symbol_info.get("filters", []):
        if f.get("filterType") == "LOT_SIZE":
            min_qty = float(f.get("minQty", min_qty))
            lot_step = float(f.get("stepSize", lot_step))
        if f.get("filterType") == "PRICE_FILTER":
            price_tick = float(f.get("tickSize", price_tick))
    return min_qty, lot_step, price_tick


def round_quantity(qty: float, min_qty: float, step_size: float) -> float:
    """Round down to step size; return 0 if below min_qty."""
    if qty <= 0:
        return 0.0
    rounded = math.floor(qty / step_size) * step_size
    if rounded < min_qty:
        return 0.0
    return round(rounded, 8)


def round_price(price: float, tick_size: float) -> float:
    """Round price to exchange tick."""
    return round(round(price / tick_size) * tick_size, 8)
