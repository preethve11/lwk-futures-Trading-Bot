"""Compare strategy variants across symbol/timeframe backtests."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from app.core.config import Settings
from app.strategies.registry import create_default_strategy_registry
from trading_bot.backtesting.engine import BacktestEngine
from trading_bot.risk.manager import RiskManager

DatasetKey = tuple[str, str]


@dataclass(frozen=True)
class StrategyComparisonRow:
    """One strategy/symbol/timeframe comparison result."""

    strategy: str
    symbol: str
    timeframe: str
    total_trades: int
    total_pnl: float
    win_rate: float
    profit_factor: float | None
    expectancy: float
    sharpe: float
    max_drawdown_pct: float
    rejection_rate: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "total_trades": self.total_trades,
            "total_pnl": _number(self.total_pnl),
            "win_rate": _number(self.win_rate),
            "profit_factor": _number(self.profit_factor),
            "expectancy": _number(self.expectancy),
            "sharpe": _number(self.sharpe),
            "max_drawdown_pct": _number(self.max_drawdown_pct),
            "rejection_rate": _number(self.rejection_rate),
        }


@dataclass(frozen=True)
class StrategyComparisonReport:
    """Portable strategy-comparison report."""

    generated_at: datetime
    baseline: str
    variants: list[str]
    rows: list[StrategyComparisonRow]

    @property
    def winner(self) -> StrategyComparisonRow | None:
        """Return the best row by positive expectancy, then profit factor."""
        candidates = [row for row in self.rows if row.total_trades > 0]
        if not candidates:
            return None
        return max(candidates, key=lambda row: (row.expectancy, row.profit_factor or 0.0, row.sharpe))

    def to_dict(self) -> dict[str, Any]:
        winner = self.winner
        return {
            "generated_at": self.generated_at.isoformat(),
            "baseline": self.baseline,
            "variants": self.variants,
            "winner": winner.to_dict() if winner is not None else None,
            "rows": [row.to_dict() for row in self.rows],
        }


class StrategyComparisonRunner:
    """Run configured strategy variants against loaded OHLCV datasets."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.registry = create_default_strategy_registry()

    def run(
        self,
        datasets: Mapping[DatasetKey, pd.DataFrame],
        *,
        baseline: str,
        variants: Sequence[str],
    ) -> StrategyComparisonReport:
        """Run baseline and variants across datasets."""
        rows: list[StrategyComparisonRow] = []
        for strategy_name in [baseline, *variants]:
            for (symbol, timeframe), candles in sorted(datasets.items()):
                rows.append(self._run_one(strategy_name, symbol, timeframe, candles))
        return StrategyComparisonReport(
            generated_at=datetime.now(timezone.utc),
            baseline=baseline,
            variants=list(variants),
            rows=rows,
        )

    def _run_one(
        self,
        strategy_name: str,
        symbol: str,
        timeframe: str,
        candles: pd.DataFrame,
    ) -> StrategyComparisonRow:
        run_settings = self.settings.model_copy(
            update={"strategy_name": strategy_name, "symbol": symbol, "timeframe": timeframe}
        )
        strategy = self.registry.create(strategy_name, run_settings)
        engine = BacktestEngine(
            strategy=strategy,
            risk_manager=_risk_manager(run_settings),
            initial_capital=run_settings.backtest_initial_capital,
            slippage_bps=run_settings.slippage_bps,
            fee_bps=run_settings.fee_bps,
            add_regime_labels_to_trades=True,
        )
        result = engine.run(
            candles,
            symbol=symbol,
            start_date=run_settings.backtest_start,
            end_date=run_settings.backtest_end,
        )
        metrics = result.metrics
        if metrics is None:
            return StrategyComparisonRow(
                strategy=strategy_name,
                symbol=symbol,
                timeframe=timeframe,
                total_trades=0,
                total_pnl=0.0,
                win_rate=0.0,
                profit_factor=None,
                expectancy=0.0,
                sharpe=0.0,
                max_drawdown_pct=0.0,
                rejection_rate=result.rejection_rate,
            )
        return StrategyComparisonRow(
            strategy=strategy_name,
            symbol=symbol,
            timeframe=timeframe,
            total_trades=metrics.total_trades,
            total_pnl=sum(trade.pnl for trade in result.trades),
            win_rate=metrics.win_rate,
            profit_factor=metrics.profit_factor,
            expectancy=metrics.expectancy,
            sharpe=metrics.sharpe_ratio,
            max_drawdown_pct=metrics.max_drawdown_pct,
            rejection_rate=result.rejection_rate,
        )


class StrategyComparisonReportExporter:
    """Write strategy comparison reports."""

    @staticmethod
    def write_json(report: StrategyComparisonReport, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report.to_dict(), indent=2, allow_nan=False), encoding="utf-8")
        return path

    @staticmethod
    def write_markdown(report: StrategyComparisonReport, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_markdown(report), encoding="utf-8")
        return path


def _risk_manager(settings: Settings) -> RiskManager:
    return RiskManager(
        risk_per_trade_usd=settings.risk_per_trade_usd,
        max_daily_loss_usd=settings.max_daily_loss_usd,
        max_drawdown_pct=settings.max_drawdown_pct,
        min_notional=settings.min_notional,
        max_position_pct_capital=settings.max_position_pct_capital,
        min_risk_reward=settings.min_risk_reward,
        use_atr_position_cap=settings.use_atr_position_cap,
        trailing_stop_atr_mult=settings.trailing_stop_atr_mult,
        symbol_info=None,
    )


def _markdown(report: StrategyComparisonReport) -> str:
    winner = report.winner
    lines = [
        "# Strategy Comparison",
        "",
        f"Generated: `{report.generated_at.isoformat()}`",
        f"Baseline: `{report.baseline}`",
        f"Variants: `{', '.join(report.variants)}`",
        "",
    ]
    if winner is not None:
        lines.extend(
            [
                "## Winner",
                "",
                f"`{winner.strategy}` on `{winner.symbol}_{winner.timeframe}` "
                f"with expectancy `{_number(winner.expectancy)}` and PF `{_number(winner.profit_factor)}`.",
                "",
            ]
        )
    lines.extend(
        [
            "## Results",
            "",
            "| Strategy | Symbol | Timeframe | Trades | PnL | Win % | PF | Expectancy | Sharpe | Rejection % |",
            "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in report.rows:
        lines.append(
            f"| {row.strategy} | {row.symbol} | {row.timeframe} | {row.total_trades} | "
            f"{_number(row.total_pnl)} | {_number(row.win_rate * 100.0)} | {_number(row.profit_factor)} | "
            f"{_number(row.expectancy)} | {_number(row.sharpe)} | {_number(row.rejection_rate * 100.0)} |"
        )
    lines.append("")
    return "\n".join(lines)


def _number(value: float | None) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    return round(value, 6)
