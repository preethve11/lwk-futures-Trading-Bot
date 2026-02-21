"""
Walk-forward optimization: split history into in-sample (train) and out-of-sample (test).
Optional: rolling windows for parameter optimization without lookahead.
"""

from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Callable, List, Optional, Any

import pandas as pd

logger = logging.getLogger("trading_bot.backtest.walk_forward")


@dataclass
class WalkForwardWindow:
    """Single train/test window."""
    train_start: int
    train_end: int
    test_start: int
    test_end: int


def split_windows(
    n_bars: int,
    train_pct: float = 0.7,
    step_bars: Optional[int] = None,
) -> List[WalkForwardWindow]:
    """
    Generate train/test splits. If step_bars is None, one split (train_pct / (1-train_pct)).
    Else rolling windows with step_bars step.
    """
    if step_bars is None:
        train_end = int(n_bars * train_pct)
        if train_end < 1 or train_end >= n_bars:
            return []
        return [WalkForwardWindow(train_start=0, train_end=train_end, test_start=train_end, test_end=n_bars)]
    windows = []
    train_len = int(n_bars * train_pct)
    start = 0
    while start + train_len < n_bars:
        test_end = min(start + train_len + step_bars, n_bars)
        windows.append(WalkForwardWindow(
            train_start=start,
            train_end=start + train_len,
            test_start=start + train_len,
            test_end=test_end,
        ))
        start += step_bars
    return windows
