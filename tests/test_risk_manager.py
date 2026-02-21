"""Unit tests for risk.manager."""

import pytest
from trading_bot.risk.manager import RiskManager, RiskResult
from trading_bot.core.types import SignalSide


def test_validate_signal_zero_stop_distance():
    rm = RiskManager(
        risk_per_trade_usd=10.0,
        max_daily_loss_usd=50.0,
        max_drawdown_pct=20.0,
        min_notional=5.0,
        max_position_pct_capital=100.0,
        min_risk_reward=1.0,
    )
    r = rm.validate_signal(100.0, 100.0, 102.0, SignalSide.LONG, 1.0)
    assert r.allowed is False
    assert "zero" in r.reason.lower()


def test_validate_signal_quantity():
    rm = RiskManager(
        risk_per_trade_usd=10.0,
        max_daily_loss_usd=50.0,
        max_drawdown_pct=20.0,
        min_notional=5.0,
        max_position_pct_capital=100.0,
        min_risk_reward=0.5,
    )
    # entry=100, stop=98 => dist=2, qty = 10/2 = 5
    r = rm.validate_signal(100.0, 98.0, 104.0, SignalSide.LONG, 1.0)
    assert r.allowed is True
    assert r.quantity == 5.0
