"""Binance testnet execution validation for live-promotion candidates."""

from __future__ import annotations

import math
import time
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

import pandas as pd
from pydantic import BaseModel, Field

from trading_bot.core.types import Position, Signal, SignalSide
from trading_bot.execution.base import ExchangeOrderStatus, OrderResult
from trading_bot.utils.exchange_filters import parse_symbol_filters, round_price


class TestnetExecutionClient(Protocol):
    """Execution client surface used by the testnet validation probe."""

    def get_klines(self, symbol: str, interval: str, limit: int = 300) -> pd.DataFrame:
        """Return recent OHLCV candles."""
        ...

    def get_symbol_info(self, symbol: str) -> dict[str, object] | None:
        """Return exchange symbol filters."""
        ...

    def set_leverage(self, symbol: str, leverage: int) -> None:
        """Set symbol leverage."""
        ...

    def get_open_position(self, symbol: str) -> Position | None:
        """Return current open position."""
        ...

    def get_open_orders(self, symbol: str) -> list[dict[str, object]]:
        """Return current open orders."""
        ...

    def place_market_and_sl_tp(self, symbol: str, signal: Signal) -> OrderResult:
        """Place market entry plus protective orders."""
        ...

    def get_order_status(self, symbol: str, order_id: str) -> ExchangeOrderStatus | None:
        """Return normalized order status."""
        ...

    def cancel_order(self, symbol: str, order_id: str) -> OrderResult:
        """Cancel an order."""
        ...

    def emergency_close_position(self, symbol: str, side: SignalSide, quantity: float) -> OrderResult:
        """Close an open position with reduce-only market order."""
        ...

    def fetch_recent_trades(self, symbol: str, limit: int = 100) -> list[dict[str, object]]:
        """Return recent account trade fills."""
        ...


class TestnetExecutionValidationReport(BaseModel):
    """Serializable outcome of one testnet execution validation probe."""

    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    strategy_name: str
    symbol: str
    timeframe: str
    side: str
    requested_notional_usd: float
    quantity: float
    expected_entry_price: float
    intended_stop_price: float
    intended_take_profit_price: float
    order_success: bool = False
    protected: bool = False
    requires_manual_review: bool = False
    entry_order_id: str | None = None
    stop_order_id: str | None = None
    take_profit_order_id: str | None = None
    entry_status: str | None = None
    stop_status: str | None = None
    take_profit_status: str | None = None
    entry_latency_ms: float | None = None
    cleanup_latency_ms: float | None = None
    actual_avg_price: float | None = None
    entry_slippage_bps: float | None = None
    entry_fee_usd: float | None = None
    entry_fee_bps: float | None = None
    fill_count: int = 0
    cancelled_order_ids: list[str] = Field(default_factory=list)
    cancel_failures: list[str] = Field(default_factory=list)
    close_success: bool = False
    close_order_id: str | None = None
    open_orders_after: int = 0
    open_position_after: bool = False
    max_fee_bps: float = 6.0
    max_slippage_bps: float = 10.0
    passed: bool = False
    violations: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    def to_json(self) -> str:
        """Return pretty JSON for file export."""
        return self.model_dump_json(indent=2)


def run_testnet_execution_validation(
    *,
    client: TestnetExecutionClient,
    strategy_name: str = "session_breakout",
    symbol: str = "ZECUSDT",
    timeframe: str = "15m",
    side: SignalSide = SignalSide.LONG,
    requested_notional_usd: float = 10.0,
    leverage: int = 1,
    stop_pct: float = 0.8,
    take_profit_pct: float = 0.8,
    max_fee_bps: float = 6.0,
    max_slippage_bps: float = 10.0,
    status_polls: int = 6,
    poll_interval_seconds: float = 0.5,
) -> TestnetExecutionValidationReport:
    """Place, verify, measure, cancel, and close one small Binance testnet probe."""
    normalized_symbol = symbol.upper()
    normalized_timeframe = timeframe.strip()
    candles = client.get_klines(normalized_symbol, normalized_timeframe, limit=100)
    expected_entry = _last_close(candles)
    symbol_info = client.get_symbol_info(normalized_symbol)
    min_qty, step_size, price_tick = parse_symbol_filters(symbol_info)
    quantity = _round_quantity_up(max(requested_notional_usd / expected_entry, min_qty), step_size, min_qty)
    signal = _build_probe_signal(
        side=side,
        expected_entry=expected_entry,
        quantity=quantity,
        stop_pct=stop_pct,
        take_profit_pct=take_profit_pct,
        price_tick=price_tick,
    )
    report = TestnetExecutionValidationReport(
        strategy_name=strategy_name,
        symbol=normalized_symbol,
        timeframe=normalized_timeframe,
        side=side.name,
        requested_notional_usd=requested_notional_usd,
        quantity=quantity,
        expected_entry_price=expected_entry,
        intended_stop_price=signal.stop_price,
        intended_take_profit_price=signal.take_profit_price,
        max_fee_bps=max_fee_bps,
        max_slippage_bps=max_slippage_bps,
    )

    preflight_violations = _preflight_clean_symbol(client, normalized_symbol)
    if preflight_violations:
        report.violations.extend(preflight_violations)
        report.passed = False
        return report

    client.set_leverage(normalized_symbol, leverage)
    placed = False
    cleanup_start = 0.0
    try:
        start = time.perf_counter()
        order_result = client.place_market_and_sl_tp(normalized_symbol, signal)
        report.entry_latency_ms = _elapsed_ms(start)
        placed = order_result.success
        report.order_success = order_result.success
        report.entry_order_id = order_result.order_id
        report.actual_avg_price = order_result.avg_price if _positive(order_result.avg_price) else None
        if order_result.protected_order is not None:
            protected = order_result.protected_order
            report.stop_order_id = protected.stop_order_id
            report.take_profit_order_id = protected.take_profit_order_id
            report.protected = protected.protected
            report.requires_manual_review = protected.requires_manual_review
        if not order_result.success:
            report.violations.append(f"entry order failed: {order_result.message}")
            return report

        _populate_order_statuses(
            report,
            client,
            normalized_symbol,
            status_polls=status_polls,
            poll_interval_seconds=poll_interval_seconds,
        )
        _populate_fill_costs(report, client.fetch_recent_trades(normalized_symbol, limit=100))
        _evaluate_execution_thresholds(report, max_fee_bps=max_fee_bps, max_slippage_bps=max_slippage_bps)
        return report
    finally:
        if placed:
            cleanup_start = time.perf_counter()
            _cleanup_probe(report, client, normalized_symbol)
            report.cleanup_latency_ms = _elapsed_ms(cleanup_start)
            _finalize_pass(report)


def write_testnet_execution_report(report: TestnetExecutionValidationReport, directory: Path) -> tuple[Path, Path]:
    """Write JSON and Markdown reports."""
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / "testnet_execution_report.json"
    markdown_path = directory / "testnet_execution_report.md"
    json_path.write_text(report.to_json() + "\n", encoding="utf-8")
    markdown_path.write_text(_markdown_report(report), encoding="utf-8")
    return json_path, markdown_path


def _last_close(candles: pd.DataFrame) -> float:
    if candles.empty or "close" not in candles.columns:
        raise ValueError("Could not fetch recent candles for testnet execution probe")
    return float(candles.iloc[-1]["close"])


def _build_probe_signal(
    *,
    side: SignalSide,
    expected_entry: float,
    quantity: float,
    stop_pct: float,
    take_profit_pct: float,
    price_tick: float,
) -> Signal:
    if side == SignalSide.LONG:
        stop = expected_entry * (1.0 - stop_pct / 100.0)
        take_profit = expected_entry * (1.0 + take_profit_pct / 100.0)
    else:
        stop = expected_entry * (1.0 + stop_pct / 100.0)
        take_profit = expected_entry * (1.0 - take_profit_pct / 100.0)
    return Signal(
        side=side,
        entry_price=expected_entry,
        stop_price=round_price(stop, price_tick),
        take_profit_price=round_price(take_profit, price_tick),
        quantity=quantity,
        timestamp=datetime.now(timezone.utc),
        metadata={"validation": "testnet_execution_probe"},
    )


def _round_quantity_up(value: float, step_size: float, min_qty: float) -> float:
    if step_size <= 0:
        return max(value, min_qty)
    steps = math.ceil(value / step_size)
    return round(max(steps * step_size, min_qty), 8)


def _preflight_clean_symbol(client: TestnetExecutionClient, symbol: str) -> list[str]:
    violations: list[str] = []
    if client.get_open_position(symbol) is not None:
        violations.append("existing open testnet position; refusing to place validation probe")
    open_orders = client.get_open_orders(symbol)
    if open_orders:
        violations.append(f"existing open testnet orders for {symbol}; refusing to place validation probe")
    return violations


def _populate_order_statuses(
    report: TestnetExecutionValidationReport,
    client: TestnetExecutionClient,
    symbol: str,
    *,
    status_polls: int,
    poll_interval_seconds: float,
) -> None:
    entry_status = _poll_order_status(client, symbol, report.entry_order_id, status_polls, poll_interval_seconds)
    stop_status = _poll_order_status(client, symbol, report.stop_order_id, status_polls, poll_interval_seconds)
    take_profit_status = _poll_order_status(
        client,
        symbol,
        report.take_profit_order_id,
        status_polls,
        poll_interval_seconds,
    )
    report.entry_status = entry_status.status if entry_status is not None else None
    report.stop_status = stop_status.status if stop_status is not None else None
    report.take_profit_status = take_profit_status.status if take_profit_status is not None else None
    if entry_status is not None and _positive(entry_status.avg_price):
        report.actual_avg_price = entry_status.avg_price
    if report.entry_status != "FILLED":
        report.violations.append(f"entry order status is {report.entry_status or 'missing'}, expected FILLED")
    if report.stop_order_id is None or report.stop_status is None:
        report.violations.append("stop-loss order was not found after entry")
    if report.take_profit_order_id is None or report.take_profit_status is None:
        report.violations.append("take-profit order was not found after entry")
    if not report.protected:
        report.violations.append("protected order result is not protected")
    if report.actual_avg_price is not None:
        report.entry_slippage_bps = _slippage_bps(
            side=SignalSide[report.side],
            expected=report.expected_entry_price,
            actual=report.actual_avg_price,
        )


def _poll_order_status(
    client: TestnetExecutionClient,
    symbol: str,
    order_id: str | None,
    status_polls: int,
    poll_interval_seconds: float,
) -> ExchangeOrderStatus | None:
    if order_id is None:
        return None
    for attempt in range(max(1, status_polls)):
        status = client.get_order_status(symbol, order_id)
        if status is not None:
            return status
        if attempt < status_polls - 1:
            time.sleep(poll_interval_seconds)
    return None


def _populate_fill_costs(report: TestnetExecutionValidationReport, fills: Sequence[dict[str, object]]) -> None:
    if report.entry_order_id is None:
        return
    entry_fills = [fill for fill in fills if str(fill.get("orderId") or "") == report.entry_order_id]
    report.fill_count = len(entry_fills)
    if not entry_fills:
        report.warnings.append("entry fill rows were not available from recent trades")
        return
    notional = 0.0
    fee = 0.0
    quantity = 0.0
    weighted_price = 0.0
    for fill in entry_fills:
        fill_qty = _float(fill.get("qty"))
        fill_price = _float(fill.get("price"))
        commission = abs(_float(fill.get("commission")))
        quantity += fill_qty
        weighted_price += fill_price * fill_qty
        notional += fill_price * fill_qty
        fee += commission
    if quantity > 0 and not _positive(report.actual_avg_price):
        report.actual_avg_price = weighted_price / quantity
        report.entry_slippage_bps = _slippage_bps(
            side=SignalSide[report.side],
            expected=report.expected_entry_price,
            actual=report.actual_avg_price,
        )
    report.entry_fee_usd = fee
    report.entry_fee_bps = (fee / notional) * 10_000.0 if notional > 0 else None


def _evaluate_execution_thresholds(
    report: TestnetExecutionValidationReport,
    *,
    max_fee_bps: float,
    max_slippage_bps: float,
) -> None:
    if report.entry_slippage_bps is None:
        report.warnings.append("entry slippage could not be measured")
    elif abs(report.entry_slippage_bps) > max_slippage_bps:
        report.violations.append(
            f"entry slippage {report.entry_slippage_bps:.2f} bps exceeds {max_slippage_bps:.2f} bps"
        )
    if report.entry_fee_bps is None:
        report.warnings.append("entry fee could not be measured")
    elif report.entry_fee_bps > max_fee_bps:
        report.violations.append(f"entry fee {report.entry_fee_bps:.2f} bps exceeds {max_fee_bps:.2f} bps")


def _cleanup_probe(report: TestnetExecutionValidationReport, client: TestnetExecutionClient, symbol: str) -> None:
    position = client.get_open_position(symbol)
    if position is not None:
        close = client.emergency_close_position(symbol, position.side, position.quantity)
        report.close_success = close.success
        report.close_order_id = close.order_id
        if not close.success:
            report.violations.append(f"emergency close failed: {close.message}")
    for order_id in [report.stop_order_id, report.take_profit_order_id]:
        if order_id is None:
            continue
        cancel = client.cancel_order(symbol, order_id)
        if cancel.success:
            report.cancelled_order_ids.append(order_id)
        else:
            report.cancel_failures.append(f"{order_id}: {cancel.message}")
    report.open_orders_after = len(client.get_open_orders(symbol))
    report.open_position_after = client.get_open_position(symbol) is not None
    if report.cancel_failures:
        report.violations.append("one or more protective order cancels failed")
    if report.open_orders_after > 0:
        report.violations.append(f"{report.open_orders_after} open orders remain after cleanup")
    if report.open_position_after:
        report.violations.append("open position remains after cleanup")


def _finalize_pass(report: TestnetExecutionValidationReport) -> None:
    report.passed = (
        report.order_success
        and report.protected
        and report.entry_status == "FILLED"
        and report.stop_status is not None
        and report.take_profit_status is not None
        and not report.open_position_after
        and report.open_orders_after == 0
        and not report.violations
    )


def _slippage_bps(*, side: SignalSide, expected: float, actual: float) -> float:
    if expected <= 0:
        return 0.0
    if side == SignalSide.LONG:
        return ((actual - expected) / expected) * 10_000.0
    return ((expected - actual) / expected) * 10_000.0


def _positive(value: float | None) -> bool:
    return value is not None and value > 0


def _elapsed_ms(start: float) -> float:
    return (time.perf_counter() - start) * 1000.0


def _float(value: object) -> float:
    if isinstance(value, (int, float, str, bytes, bytearray)):
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0
    return 0.0


def _markdown_report(report: TestnetExecutionValidationReport) -> str:
    status = "PASS" if report.passed else "FAIL"
    lines = [
        "# Testnet Execution Validation",
        "",
        f"Status: `{status}`",
        f"Generated: `{report.generated_at.isoformat()}`",
        f"Candidate: `{report.strategy_name}_{report.symbol}_{report.timeframe}`",
        "",
        "## Order Probe",
        "",
        f"- Side: `{report.side}`",
        f"- Quantity: `{report.quantity}`",
        f"- Requested notional: `{report.requested_notional_usd}`",
        f"- Expected entry: `{report.expected_entry_price}`",
        f"- Actual avg entry: `{report.actual_avg_price}`",
        f"- Entry latency ms: `{report.entry_latency_ms}`",
        f"- Entry slippage bps: `{report.entry_slippage_bps}`",
        f"- Entry fee bps: `{report.entry_fee_bps}`",
        "",
        "## Protection",
        "",
        f"- Entry order: `{report.entry_order_id}` status `{report.entry_status}`",
        f"- Stop order: `{report.stop_order_id}` status `{report.stop_status}`",
        f"- Take-profit order: `{report.take_profit_order_id}` status `{report.take_profit_status}`",
        f"- Protected: `{report.protected}`",
        "",
        "## Cleanup",
        "",
        f"- Cancelled orders: `{', '.join(report.cancelled_order_ids)}`",
        f"- Close success: `{report.close_success}`",
        f"- Open orders after: `{report.open_orders_after}`",
        f"- Open position after: `{report.open_position_after}`",
        "",
        "## Violations",
        "",
    ]
    lines.extend([f"- {violation}" for violation in report.violations] or ["- None"])
    lines.extend(["", "## Warnings", ""])
    lines.extend([f"- {warning}" for warning in report.warnings] or ["- None"])
    lines.append("")
    return "\n".join(lines)
