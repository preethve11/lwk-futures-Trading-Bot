"""Basic meta-strategy allocator."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StrategyHealthInput:
    """Inputs used to allocate or disable a strategy."""

    strategy_id: str
    status: str
    expectancy: float
    max_drawdown_pct: float
    correlation_bucket: str = ""


@dataclass(frozen=True)
class AllocationDecision:
    """Capital allocation decision for one strategy."""

    strategy_id: str
    weight: float
    allocated_capital: float
    active: bool
    reason: str


class EqualWeightMetaAllocator:
    """Equal-weight allocator with hard max weight and health-based deallocation."""

    def __init__(self, *, max_weight: float = 0.30) -> None:
        self.max_weight = max_weight

    def allocate(self, *, capital: float, strategies: list[StrategyHealthInput]) -> list[AllocationDecision]:
        """Allocate capital across healthy strategies."""
        eligible = [
            strategy
            for strategy in strategies
            if strategy.status.upper() in {"HEALTHY", "WARNING"} and strategy.expectancy > 0
        ]
        if not eligible:
            return [
                AllocationDecision(
                    strategy_id=strategy.strategy_id,
                    weight=0.0,
                    allocated_capital=0.0,
                    active=False,
                    reason="Strategy disabled because health or expectancy is unacceptable",
                )
                for strategy in strategies
            ]
        equal_weight = min(self.max_weight, 1.0 / len(eligible))
        decisions: list[AllocationDecision] = []
        for strategy in strategies:
            if strategy not in eligible:
                decisions.append(
                    AllocationDecision(
                        strategy_id=strategy.strategy_id,
                        weight=0.0,
                        allocated_capital=0.0,
                        active=False,
                        reason="Strategy disabled because health or expectancy is unacceptable",
                    )
                )
                continue
            weight = equal_weight * 0.5 if strategy.status.upper() == "WARNING" else equal_weight
            decisions.append(
                AllocationDecision(
                    strategy_id=strategy.strategy_id,
                    weight=weight,
                    allocated_capital=capital * weight,
                    active=weight > 0,
                    reason="Equal-weight allocation capped by max strategy weight",
                )
            )
        return decisions
