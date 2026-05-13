"""Live/paper strategy health classification."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class StrategyHealthStatus(str, Enum):
    """Operator health state for a strategy."""

    HEALTHY = "HEALTHY"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    KILLED = "KILLED"


@dataclass(frozen=True)
class StrategyHealthSnapshot:
    """Computed strategy health output."""

    status: StrategyHealthStatus
    reason: str
    degradation_pct: float


class PerformanceHealthTracker:
    """Compare live/paper performance against promotion thresholds and backtest baseline."""

    def __init__(
        self,
        *,
        min_trades: int = 20,
        min_expectancy: float = 0.0,
        min_profit_factor: float = 1.1,
        max_drawdown_pct: float = 20.0,
        max_slippage_bps: float = 10.0,
    ) -> None:
        self.min_trades = min_trades
        self.min_expectancy = min_expectancy
        self.min_profit_factor = min_profit_factor
        self.max_drawdown_pct = max_drawdown_pct
        self.max_slippage_bps = max_slippage_bps

    def classify(
        self,
        *,
        trade_count: int,
        expectancy: float,
        profit_factor: float,
        max_drawdown_pct: float,
        slippage_bps: float,
        backtest_expectancy: float | None = None,
    ) -> StrategyHealthSnapshot:
        """Classify current strategy health."""
        degradation = _degradation_pct(backtest_expectancy, expectancy)
        if max_drawdown_pct >= self.max_drawdown_pct:
            return StrategyHealthSnapshot(StrategyHealthStatus.KILLED, "Drawdown exceeded hard limit", degradation)
        if trade_count >= self.min_trades and expectancy < self.min_expectancy:
            return StrategyHealthSnapshot(StrategyHealthStatus.CRITICAL, "Live expectancy is negative after enough trades", degradation)
        if slippage_bps > self.max_slippage_bps:
            return StrategyHealthSnapshot(StrategyHealthStatus.CRITICAL, "Slippage exceeds edge budget", degradation)
        if trade_count >= self.min_trades and profit_factor < self.min_profit_factor:
            return StrategyHealthSnapshot(StrategyHealthStatus.WARNING, "Profit factor is below promotion threshold", degradation)
        if degradation > 50.0:
            return StrategyHealthSnapshot(StrategyHealthStatus.WARNING, "Live expectancy has degraded versus backtest", degradation)
        return StrategyHealthSnapshot(StrategyHealthStatus.HEALTHY, "Performance is within configured limits", degradation)


def _degradation_pct(backtest_expectancy: float | None, live_expectancy: float) -> float:
    if backtest_expectancy is None or backtest_expectancy <= 0:
        return 0.0
    return max(0.0, ((backtest_expectancy - live_expectancy) / backtest_expectancy) * 100.0)
