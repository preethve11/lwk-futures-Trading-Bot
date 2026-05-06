"""Monte Carlo risk simulation from historical trade outcomes."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import numpy as np


@dataclass(frozen=True)
class DistributionSummary:
    """Portable summary statistics for one simulated distribution."""

    mean: float
    stdev: float
    minimum: float
    percentile_5: float
    percentile_50: float
    percentile_95: float
    maximum: float

    def to_dict(self) -> dict[str, float]:
        return {
            "mean": self.mean,
            "stdev": self.stdev,
            "min": self.minimum,
            "p05": self.percentile_5,
            "p50": self.percentile_50,
            "p95": self.percentile_95,
            "max": self.maximum,
        }


@dataclass(frozen=True)
class MonteCarloReport:
    """Monte Carlo simulation report."""

    initial_capital: float
    simulations: int
    horizon_trades: int
    ruin_drawdown_pct: float
    probability_of_ruin: float
    input_trade_count: int
    input_trade_pnls: list[float]
    final_capital: DistributionSummary
    total_return_pct: DistributionSummary
    max_drawdown_pct: DistributionSummary
    final_capital_distribution: list[float]
    total_return_pct_distribution: list[float]
    max_drawdown_pct_distribution: list[float]
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, object]:
        return {
            "generated_at": self.generated_at.isoformat(),
            "initial_capital": self.initial_capital,
            "simulations": self.simulations,
            "horizon_trades": self.horizon_trades,
            "ruin_drawdown_pct": self.ruin_drawdown_pct,
            "probability_of_ruin": self.probability_of_ruin,
            "input_trade_count": self.input_trade_count,
            "input_trade_pnls": self.input_trade_pnls,
            "confidence_intervals": {
                "final_capital": {
                    "p05": self.final_capital.percentile_5,
                    "p50": self.final_capital.percentile_50,
                    "p95": self.final_capital.percentile_95,
                },
                "total_return_pct": {
                    "p05": self.total_return_pct.percentile_5,
                    "p50": self.total_return_pct.percentile_50,
                    "p95": self.total_return_pct.percentile_95,
                },
                "max_drawdown_pct": {
                    "p05": self.max_drawdown_pct.percentile_5,
                    "p50": self.max_drawdown_pct.percentile_50,
                    "p95": self.max_drawdown_pct.percentile_95,
                },
            },
            "summary": {
                "final_capital": self.final_capital.to_dict(),
                "total_return_pct": self.total_return_pct.to_dict(),
                "max_drawdown_pct": self.max_drawdown_pct.to_dict(),
            },
            "distributions": {
                "final_capital": self.final_capital_distribution,
                "total_return_pct": self.total_return_pct_distribution,
                "max_drawdown_pct": self.max_drawdown_pct_distribution,
            },
        }


class MonteCarloSimulator:
    """Resample trade PnLs to estimate forward equity risk."""

    def __init__(
        self,
        *,
        initial_capital: float,
        simulations: int = 1_000,
        horizon_trades: int = 100,
        ruin_drawdown_pct: float = 30.0,
        random_seed: int = 42,
    ) -> None:
        if initial_capital <= 0:
            raise ValueError("initial_capital must be greater than zero")
        if simulations <= 0:
            raise ValueError("simulations must be greater than zero")
        if horizon_trades <= 0:
            raise ValueError("horizon_trades must be greater than zero")
        if ruin_drawdown_pct < 0 or ruin_drawdown_pct > 100:
            raise ValueError("ruin_drawdown_pct must be between 0 and 100")
        self.initial_capital = initial_capital
        self.simulations = simulations
        self.horizon_trades = horizon_trades
        self.ruin_drawdown_pct = ruin_drawdown_pct
        self.random_seed = random_seed

    def run(self, trade_pnls: list[float]) -> MonteCarloReport:
        """Run simulations by sampling trade PnLs with replacement."""
        if not trade_pnls:
            raise ValueError("Monte Carlo simulation requires at least one trade PnL")
        pnls = np.array(trade_pnls, dtype=float)
        rng = np.random.default_rng(self.random_seed)
        ruin_equity = self.initial_capital * (1.0 - self.ruin_drawdown_pct / 100.0)
        final_capitals: list[float] = []
        total_return_pcts: list[float] = []
        max_drawdowns: list[float] = []
        ruined = 0

        for _ in range(self.simulations):
            sampled = rng.choice(pnls, size=self.horizon_trades, replace=True)
            equity_curve = np.concatenate(([self.initial_capital], self.initial_capital + np.cumsum(sampled)))
            final_capital = float(equity_curve[-1])
            max_drawdown = _max_drawdown_pct(equity_curve)
            if float(np.min(equity_curve)) <= ruin_equity:
                ruined += 1
            final_capitals.append(final_capital)
            total_return_pcts.append(((final_capital / self.initial_capital) - 1.0) * 100.0)
            max_drawdowns.append(max_drawdown)

        return MonteCarloReport(
            initial_capital=self.initial_capital,
            simulations=self.simulations,
            horizon_trades=self.horizon_trades,
            ruin_drawdown_pct=self.ruin_drawdown_pct,
            probability_of_ruin=ruined / self.simulations,
            input_trade_count=len(trade_pnls),
            input_trade_pnls=[float(value) for value in trade_pnls],
            final_capital=_summarize(final_capitals),
            total_return_pct=_summarize(total_return_pcts),
            max_drawdown_pct=_summarize(max_drawdowns),
            final_capital_distribution=final_capitals,
            total_return_pct_distribution=total_return_pcts,
            max_drawdown_pct_distribution=max_drawdowns,
        )


class MonteCarloReportExporter:
    """Write Monte Carlo reports to JSON."""

    @staticmethod
    def write_json(report: MonteCarloReport, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(report.to_dict(), handle, indent=2, allow_nan=False)
            handle.write("\n")
        return path


def load_trade_pnls_json(path: Path, *, initial_capital: float) -> list[float]:
    """Load trade PnLs from a JSON list, object, or backtest report equity curve."""
    with open(path, "r", encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    return _extract_trade_pnls(payload, initial_capital=initial_capital)


def _extract_trade_pnls(payload: Any, *, initial_capital: float) -> list[float]:
    if isinstance(payload, list):
        return _number_list(payload)
    if not isinstance(payload, dict):
        raise ValueError("Monte Carlo JSON input must be a list or object")

    if isinstance(payload.get("pnls"), list):
        return _number_list(payload["pnls"])
    if isinstance(payload.get("trade_pnls"), list):
        return _number_list(payload["trade_pnls"])
    if isinstance(payload.get("returns"), list):
        return [value * initial_capital for value in _number_list(payload["returns"])]
    if isinstance(payload.get("equity_curve"), list):
        return _pnls_from_equity_curve(_number_list(payload["equity_curve"]))

    aggregate = payload.get("aggregate")
    if isinstance(aggregate, dict) and isinstance(aggregate.get("equity_curve"), list):
        return _pnls_from_equity_curve(_number_list(aggregate["equity_curve"]))

    raise ValueError("Monte Carlo JSON input must include pnls, trade_pnls, returns, or equity_curve")


def _number_list(values: list[object]) -> list[float]:
    numbers: list[float] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ValueError("Monte Carlo input values must be numeric")
        numbers.append(float(value))
    if not numbers:
        raise ValueError("Monte Carlo input must include at least one numeric value")
    return numbers


def _pnls_from_equity_curve(equity_curve: list[float]) -> list[float]:
    if len(equity_curve) < 2:
        raise ValueError("Equity curve input must include at least two points")
    return [current - previous for previous, current in zip(equity_curve, equity_curve[1:])]


def _summarize(values: list[float]) -> DistributionSummary:
    arr = np.array(values, dtype=float)
    return DistributionSummary(
        mean=float(np.mean(arr)),
        stdev=float(np.std(arr)),
        minimum=float(np.min(arr)),
        percentile_5=float(np.percentile(arr, 5)),
        percentile_50=float(np.percentile(arr, 50)),
        percentile_95=float(np.percentile(arr, 95)),
        maximum=float(np.max(arr)),
    )


def _max_drawdown_pct(equity_curve: np.ndarray[Any, np.dtype[np.float64]]) -> float:
    peak = np.maximum.accumulate(equity_curve)
    drawdowns = (peak - equity_curve) / np.where(peak != 0, peak, 1.0)
    return float(np.max(drawdowns) * 100.0)
