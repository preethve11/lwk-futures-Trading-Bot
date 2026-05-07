from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from app.ops.testnet_execution import run_testnet_execution_validation
from trading_bot.core.types import Position, Signal, SignalSide
from trading_bot.execution.base import ExchangeOrderStatus, OrderResult, ProtectedOrderResult


class FakeTestnetClient:
    def __init__(
        self,
        *,
        protected: bool = True,
        existing_position: bool = False,
        existing_orders: bool = False,
        avg_price: float = 100.05,
        commission: float = 0.004002,
    ) -> None:
        self.protected = protected
        self.position: Position | None = (
            Position(symbol="ZECUSDT", side=SignalSide.LONG, quantity=0.1, entry_price=100.0)
            if existing_position
            else None
        )
        self.open_orders: dict[str, dict[str, object]] = (
            {"existing-order": {"orderId": "existing-order"}} if existing_orders else {}
        )
        self.avg_price = avg_price
        self.commission = commission
        self.place_calls = 0
        self.cancelled_order_ids: list[str] = []
        self.close_calls = 0

    def get_klines(self, symbol: str, interval: str, limit: int = 300) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "time": pd.Timestamp("2026-01-01T00:00:00Z"),
                    "open": 99.0,
                    "high": 101.0,
                    "low": 98.0,
                    "close": 100.0,
                    "volume": 1000.0,
                }
            ]
        )

    def get_symbol_info(self, symbol: str) -> dict[str, object]:
        return {
            "filters": [
                {"filterType": "LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
            ]
        }

    def set_leverage(self, symbol: str, leverage: int) -> None:
        return None

    def get_open_position(self, symbol: str) -> Position | None:
        return self.position

    def get_open_orders(self, symbol: str) -> list[dict[str, object]]:
        return list(self.open_orders.values())

    def place_market_and_sl_tp(self, symbol: str, signal: Signal) -> OrderResult:
        self.place_calls += 1
        self.position = Position(
            symbol=symbol,
            side=signal.side,
            quantity=signal.quantity,
            entry_price=self.avg_price,
        )
        protected_order = ProtectedOrderResult(
            entry_order_id="entry-1",
            stop_order_id="stop-1" if self.protected else None,
            take_profit_order_id="tp-1" if self.protected else None,
            protected=self.protected,
            requires_manual_review=not self.protected,
            message="protected" if self.protected else "missing protection",
        )
        if self.protected:
            self.open_orders = {
                "stop-1": {"orderId": "stop-1", "type": "STOP_MARKET", "reduceOnly": True},
                "tp-1": {"orderId": "tp-1", "type": "LIMIT", "reduceOnly": True},
            }
        return OrderResult(
            success=True,
            order_id="entry-1",
            avg_price=self.avg_price,
            quantity=signal.quantity,
            message="placed",
            protected_order=protected_order,
        )

    def get_order_status(self, symbol: str, order_id: str) -> ExchangeOrderStatus | None:
        if order_id == "entry-1":
            return ExchangeOrderStatus(
                order_id=order_id,
                symbol=symbol,
                status="FILLED",
                order_type="MARKET",
                side="BUY",
                executed_quantity=0.1,
                avg_price=self.avg_price,
                update_time=datetime.now(timezone.utc),
            )
        if order_id in {"stop-1", "tp-1"}:
            return ExchangeOrderStatus(
                order_id=order_id,
                symbol=symbol,
                status="NEW",
                order_type="STOP_MARKET" if order_id == "stop-1" else "LIMIT",
                side="SELL",
                reduce_only=True,
                update_time=datetime.now(timezone.utc),
            )
        return None

    def cancel_order(self, symbol: str, order_id: str) -> OrderResult:
        self.cancelled_order_ids.append(order_id)
        self.open_orders.pop(order_id, None)
        return OrderResult(success=True, order_id=order_id, message="CANCELED")

    def emergency_close_position(self, symbol: str, side: SignalSide, quantity: float) -> OrderResult:
        self.close_calls += 1
        self.position = None
        return OrderResult(success=True, order_id="close-1", avg_price=self.avg_price, quantity=quantity)

    def fetch_recent_trades(self, symbol: str, limit: int = 100) -> list[dict[str, object]]:
        return [
            {
                "orderId": "entry-1",
                "price": str(self.avg_price),
                "qty": "0.1",
                "commission": str(self.commission),
            }
        ]


def test_testnet_execution_validation_passes_protected_small_notional_probe() -> None:
    client = FakeTestnetClient()

    report = run_testnet_execution_validation(
        client=client,
        requested_notional_usd=10.0,
        status_polls=1,
        poll_interval_seconds=0,
    )

    assert report.passed is True
    assert report.protected is True
    assert report.entry_status == "FILLED"
    assert report.stop_status == "NEW"
    assert report.take_profit_status == "NEW"
    assert report.entry_slippage_bps == pytest.approx(5.0)
    assert report.entry_fee_bps == pytest.approx(4.0)
    assert report.cancelled_order_ids == ["stop-1", "tp-1"]
    assert report.close_success is True
    assert report.open_position_after is False
    assert report.open_orders_after == 0


def test_testnet_execution_validation_fails_and_closes_when_protection_missing() -> None:
    client = FakeTestnetClient(protected=False)

    report = run_testnet_execution_validation(
        client=client,
        requested_notional_usd=10.0,
        status_polls=1,
        poll_interval_seconds=0,
    )

    assert report.passed is False
    assert report.requires_manual_review is True
    assert report.close_success is True
    assert client.close_calls == 1
    assert any("stop-loss order was not found" in violation for violation in report.violations)
    assert any("take-profit order was not found" in violation for violation in report.violations)
    assert any("protected order result is not protected" in violation for violation in report.violations)


def test_testnet_execution_validation_refuses_dirty_symbol_preflight() -> None:
    client = FakeTestnetClient(existing_orders=True)

    report = run_testnet_execution_validation(
        client=client,
        requested_notional_usd=10.0,
        status_polls=1,
        poll_interval_seconds=0,
    )

    assert report.passed is False
    assert client.place_calls == 0
    assert any("existing open testnet orders" in violation for violation in report.violations)
