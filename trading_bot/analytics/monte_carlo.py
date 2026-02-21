"""
Monte Carlo simulation: shuffle trade order or bootstrap returns to estimate
distribution of outcomes (e.g. max drawdown, final equity).
"""

from __future__ import annotations
import random
from typing import List, Optional

from trading_bot.analytics.metrics import max_drawdown, compute_metrics


def monte_carlo_trades(pnls: List[float], n_simulations: int = 1000, seed: Optional[int] = None) -> List[float]:
    """
    Shuffle trade PnLs and compute total return for each simulation.
    Returns list of final equity ratios (1 + total_pnl / initial_capital if capital=1).
    """
    if seed is not None:
        random.seed(seed)
    if not pnls:
        return []
    results = []
    for _ in range(n_simulations):
        shuffled = pnls.copy()
        random.shuffle(shuffled)
        equity = 1.0
        for p in shuffled:
            equity += p
        results.append(equity)
    return results


def monte_carlo_drawdowns(pnls: List[float], n_simulations: int = 1000, seed: Optional[int] = None) -> List[float]:
    """Return list of max drawdown % for each shuffled sequence."""
    if seed is not None:
        random.seed(seed)
    if not pnls:
        return []
    dd_list = []
    for _ in range(n_simulations):
        shuffled = pnls.copy()
        random.shuffle(shuffled)
        cum = [1.0]
        for p in shuffled:
            cum.append(cum[-1] + p)
        dd_list.append(max_drawdown(cum))
    return dd_list
