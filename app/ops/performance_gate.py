"""Strategy performance gate for live-trading governance."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.persistence.models import BacktestRunModel


@dataclass(frozen=True)
class PerformanceGateViolation:
    """One failed performance requirement."""

    field: str
    actual: float | int | str | None
    required: float | int | str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "actual": self.actual,
            "required": self.required,
            "message": self.message,
        }


@dataclass(frozen=True)
class StrategyPerformanceGateResult:
    """Decision object for strategy live-readiness."""

    allowed: bool
    reason: str
    backtest_run_id: str | None = None
    symbol: str | None = None
    strategy_name: str | None = None
    metrics: dict[str, float | int | None] = field(default_factory=dict)
    violations: list[PerformanceGateViolation] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "backtest_run_id": self.backtest_run_id,
            "symbol": self.symbol,
            "strategy_name": self.strategy_name,
            "metrics": self.metrics,
            "violations": [violation.to_dict() for violation in self.violations],
        }


def evaluate_strategy_performance_gate(session: Session, settings: Settings) -> StrategyPerformanceGateResult:
    """Evaluate the latest relevant backtest run against configured live-gate thresholds."""
    run = _latest_relevant_backtest(session, settings)
    if run is None:
        return StrategyPerformanceGateResult(
            allowed=False,
            reason="No backtest run found for configured strategy/symbol",
            strategy_name=settings.strategy_name,
            symbol=settings.symbol,
            violations=[
                PerformanceGateViolation(
                    field="backtest_run",
                    actual=None,
                    required="latest relevant backtest",
                    message="Run and persist a backtest before enabling live trading.",
                )
            ],
        )

    violations: list[PerformanceGateViolation] = []
    _require_minimum(
        violations,
        field="total_trades",
        actual=run.total_trades,
        required=settings.live_gate_min_trades,
        message="Backtest sample is too small for live promotion.",
    )
    _require_minimum(
        violations,
        field="profit_factor",
        actual=run.profit_factor,
        required=settings.live_gate_min_profit_factor,
        message="Profit factor is below the live promotion threshold.",
    )
    _require_minimum(
        violations,
        field="expectancy",
        actual=run.expectancy,
        required=settings.live_gate_min_expectancy_usd,
        message="Average trade expectancy is below the live promotion threshold.",
    )
    _require_minimum(
        violations,
        field="sharpe_ratio",
        actual=run.sharpe_ratio,
        required=settings.live_gate_min_sharpe,
        message="Sharpe ratio is below the live promotion threshold.",
    )
    drawdown = abs(run.max_drawdown_pct)
    if drawdown > settings.live_gate_max_drawdown_pct:
        violations.append(
            PerformanceGateViolation(
                field="max_drawdown_pct",
                actual=drawdown,
                required=settings.live_gate_max_drawdown_pct,
                message="Backtest drawdown exceeds the live promotion threshold.",
            )
        )
    age_days = _age_days(run.created_at)
    if age_days > settings.live_gate_max_backtest_age_days:
        violations.append(
            PerformanceGateViolation(
                field="backtest_age_days",
                actual=round(age_days, 2),
                required=settings.live_gate_max_backtest_age_days,
                message="Backtest result is too old for live promotion.",
            )
        )

    allowed = not violations
    reason = "Strategy performance gate passed" if allowed else "Strategy performance gate failed"
    return StrategyPerformanceGateResult(
        allowed=allowed,
        reason=reason,
        backtest_run_id=run.run_id,
        symbol=run.symbol,
        strategy_name=run.strategy_name,
        metrics={
            "total_trades": run.total_trades,
            "total_return_pct": run.total_return_pct,
            "profit_factor": run.profit_factor,
            "expectancy": run.expectancy,
            "sharpe_ratio": run.sharpe_ratio,
            "sortino_ratio": run.sortino_ratio,
            "max_drawdown_pct": run.max_drawdown_pct,
            "win_rate": run.win_rate,
            "age_days": round(age_days, 2),
        },
        violations=violations,
    )


def format_strategy_performance_gate(result: StrategyPerformanceGateResult) -> str:
    """Render a CLI-friendly strategy performance gate report."""
    status = "PASS" if result.allowed else "FAIL"
    lines = [f"--- Strategy Performance Gate: {status} ---", result.reason]
    if result.backtest_run_id is not None:
        lines.append(f"Run: {result.backtest_run_id} ({result.strategy_name} {result.symbol})")
    if result.metrics:
        lines.append("Metrics:")
        for key, value in result.metrics.items():
            lines.append(f"  {key}: {value}")
    if result.violations:
        lines.append("Violations:")
        for violation in result.violations:
            lines.append(f"  [{violation.field}] actual={violation.actual} required={violation.required} - {violation.message}")
    return "\n".join(lines)


def _latest_relevant_backtest(session: Session, settings: Settings) -> BacktestRunModel | None:
    statement = (
        select(BacktestRunModel)
        .where(BacktestRunModel.strategy_name == settings.strategy_name)
        .where(BacktestRunModel.symbol.in_([settings.symbol, "MULTI"]))
        .order_by(BacktestRunModel.created_at.desc(), BacktestRunModel.id.desc())
        .limit(1)
    )
    return session.scalar(statement)


def _require_minimum(
    violations: list[PerformanceGateViolation],
    *,
    field: str,
    actual: float | int,
    required: float | int,
    message: str,
) -> None:
    if actual >= required:
        return
    violations.append(
        PerformanceGateViolation(
            field=field,
            actual=actual,
            required=required,
            message=message,
        )
    )


def _age_days(value: datetime) -> float:
    created_at = value
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - created_at).total_seconds() / 86_400)
