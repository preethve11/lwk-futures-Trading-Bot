"""
Performance metrics: Sharpe, Sortino, max drawdown, win rate, profit factor, expectancy.
Assumes period returns (e.g. daily or per-trade).
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional

import numpy as np


@dataclass
class PerformanceMetrics:
    """Aggregate performance metrics."""
    total_return_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown_pct: float
    win_rate: float
    profit_factor: float
    expectancy: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    avg_win: float
    avg_loss: float


def sharpe_ratio(returns: List[float], risk_free_rate: float = 0.0, periods_per_year: float = 252.0) -> float:
    """Annualized Sharpe. returns = list of period returns."""
    if not returns:
        return 0.0
    arr = np.array(returns)
    excess = arr - risk_free_rate / periods_per_year
    if excess.std() <= 1e-12:
        return 0.0
    return float(np.sqrt(periods_per_year) * excess.mean() / excess.std())


def sortino_ratio(returns: List[float], risk_free_rate: float = 0.0, periods_per_year: float = 252.0) -> float:
    """Annualized Sortino (downside deviation)."""
    if not returns:
        return 0.0
    arr = np.array(returns)
    excess = arr - risk_free_rate / periods_per_year
    downside = arr[arr < 0]
    if len(downside) == 0 or downside.std() <= 1e-12:
        return sharpe_ratio(returns, risk_free_rate, periods_per_year)
    return float(np.sqrt(periods_per_year) * excess.mean() / downside.std())


def max_drawdown(cumulative_returns: List[float]) -> float:
    """Max drawdown in percent (e.g. 0.15 = 15%)."""
    if not cumulative_returns:
        return 0.0
    arr = np.array(cumulative_returns)
    peak = np.maximum.accumulate(arr)
    dd = (arr - peak) / np.where(peak != 0, peak, 1)
    return float(np.min(dd)) * 100.0


def win_rate(pnls: List[float]) -> float:
    """Fraction of trades with positive PnL."""
    if not pnls:
        return 0.0
    return sum(1 for p in pnls if p > 0) / len(pnls)


def profit_factor(pnls: List[float]) -> float:
    """Gross profit / gross loss. Returns 0 if no losses."""
    wins = sum(p for p in pnls if p > 0)
    losses = sum(-p for p in pnls if p < 0)
    if losses <= 0:
        return float("inf") if wins > 0 else 0.0
    return wins / losses


def expectancy(pnls: List[float]) -> float:
    """Average PnL per trade."""
    if not pnls:
        return 0.0
    return sum(pnls) / len(pnls)


def compute_metrics(
    pnls: List[float],
    cumulative_returns: Optional[List[float]] = None,
    risk_free_rate: float = 0.0,
    periods_per_year: float = 252.0,
) -> PerformanceMetrics:
    """
    Compute full metrics from list of trade PnLs.
    cumulative_returns: optional (e.g. equity curve as returns). If None, derived from pnls assuming initial capital.
    """
    total_trades = len(pnls)
    if total_trades == 0:
        return PerformanceMetrics(
            total_return_pct=0.0, sharpe_ratio=0.0, sortino_ratio=0.0, max_drawdown_pct=0.0,
            win_rate=0.0, profit_factor=0.0, expectancy=0.0,
            total_trades=0, winning_trades=0, losing_trades=0, avg_win=0.0, avg_loss=0.0,
        )
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    total_pnl = sum(pnls)
    if cumulative_returns is None:
        # Build equity curve from pnls (1 + running sum) for drawdown
        equity = 1.0
        cum_ret = []
        for p in pnls:
            equity += p
            cum_ret.append(equity)
        cumulative_returns = cum_ret
    rets = np.diff([1.0] + cumulative_returns) if len(cumulative_returns) > 1 else [total_pnl]
    if not isinstance(rets, list):
        rets = rets.tolist()
    total_return_pct = (cumulative_returns[-1] - 1.0) * 100.0
    return PerformanceMetrics(
        total_return_pct=total_return_pct,
        sharpe_ratio=sharpe_ratio(rets, risk_free_rate, periods_per_year),
        sortino_ratio=sortino_ratio(rets, risk_free_rate, periods_per_year),
        max_drawdown_pct=max_drawdown(cumulative_returns),
        win_rate=win_rate(pnls),
        profit_factor=profit_factor(pnls),
        expectancy=expectancy(pnls),
        total_trades=total_trades,
        winning_trades=len(wins),
        losing_trades=len(losses),
        avg_win=sum(wins) / len(wins) if wins else 0.0,
        avg_loss=sum(losses) / len(losses) if losses else 0.0,
    )
