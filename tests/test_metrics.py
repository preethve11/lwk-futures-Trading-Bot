"""Unit tests for analytics.metrics."""

import pytest
from trading_bot.analytics.metrics import (
    sharpe_ratio,
    sortino_ratio,
    max_drawdown,
    win_rate,
    profit_factor,
    expectancy,
    compute_metrics,
)


def test_sharpe_ratio_empty():
    assert sharpe_ratio([]) == 0.0


def test_sharpe_ratio_constant():
    assert sharpe_ratio([0.01] * 10) == 0.0  # zero std


def test_win_rate():
    assert win_rate([1, -1, 1, 1]) == 0.75
    assert win_rate([]) == 0.0


def test_profit_factor():
    assert profit_factor([10, -5, 10, -5]) == 2.0
    assert profit_factor([10, 10]) == float("inf")
    assert profit_factor([-5, -5]) == 0.0


def test_expectancy():
    assert expectancy([10, -5, 5]) == pytest.approx(10 / 3)
    assert expectancy([]) == 0.0


def test_max_drawdown():
    # equity 1 -> 1.2 -> 1.0 -> 1.1  =>  peak 1.2, dd (1.0-1.2)/1.2 = -16.67%
    cum = [1.0, 1.2, 1.0, 1.1]
    assert max_drawdown(cum) == pytest.approx(-16.666, rel=0.01)


def test_compute_metrics():
    pnls = [10.0, -5.0, 15.0, -3.0]
    m = compute_metrics(pnls)
    assert m.total_trades == 4
    assert m.winning_trades == 2
    assert m.losing_trades == 2
    assert m.expectancy == pytest.approx(4.25)
    assert m.win_rate == 0.5
