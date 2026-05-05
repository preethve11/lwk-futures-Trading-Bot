"""Multi-symbol backtest orchestration and report export."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Mapping

import pandas as pd
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.persistence.models import BacktestRunModel
from app.persistence.repositories import TradeRepository
from app.strategies.registry import create_default_strategy_registry
from trading_bot.analytics.metrics import PerformanceMetrics, compute_metrics
from trading_bot.backtesting.engine import BacktestEngine, BacktestResult
from trading_bot.core.types import Trade
from trading_bot.risk.manager import RiskManager


@dataclass(frozen=True)
class BacktestReport:
    """Serializable report for one symbol or an aggregate multi-symbol run."""

    symbol: str
    timeframe: str
    initial_capital: float
    final_capital: float
    total_pnl: float
    total_trades: int
    metrics: PerformanceMetrics
    equity_curve: list[float]
    run_id: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "initial_capital": self.initial_capital,
            "final_capital": self.final_capital,
            "total_pnl": self.total_pnl,
            "total_trades": self.total_trades,
            "run_id": self.run_id,
            "metrics": metrics_to_dict(self.metrics),
            "equity_curve": self.equity_curve,
        }


@dataclass(frozen=True)
class MultiSymbolBacktestReport:
    """Serializable report containing per-symbol and aggregate performance."""

    aggregate: BacktestReport
    symbols: list[BacktestReport]
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, object]:
        return {
            "generated_at": self.generated_at.isoformat(),
            "aggregate": self.aggregate.to_dict(),
            "symbols": [symbol_report.to_dict() for symbol_report in self.symbols],
        }


class MultiSymbolBacktestRunner:
    """Run one configured strategy across multiple symbol data sets."""

    def __init__(self, settings: Settings, session: Session | None = None) -> None:
        self.settings = settings
        self.session = session

    def run(
        self,
        datasets: Mapping[str, pd.DataFrame],
        *,
        timeframe: str | None = None,
        start_date: str | datetime | None = None,
        end_date: str | datetime | None = None,
    ) -> MultiSymbolBacktestReport:
        if not datasets:
            raise ValueError("Multi-symbol backtest requires at least one symbol data set")

        resolved_timeframe = timeframe or self.settings.timeframe
        symbol_reports: list[BacktestReport] = []
        all_trades: list[Trade] = []

        for symbol, candles in datasets.items():
            normalized_symbol = symbol.strip().upper()
            result = self._run_symbol(
                normalized_symbol,
                candles,
                start_date=start_date,
                end_date=end_date,
            )
            run_model = self._persist_symbol_run(
                symbol=normalized_symbol,
                timeframe=resolved_timeframe,
                result=result,
                start_date=start_date,
                end_date=end_date,
                source="multi_symbol",
            )
            final_capital = result.equity_curve[-1] if result.equity_curve else self.settings.backtest_initial_capital
            symbol_reports.append(
                BacktestReport(
                    symbol=normalized_symbol,
                    timeframe=resolved_timeframe,
                    initial_capital=self.settings.backtest_initial_capital,
                    final_capital=final_capital,
                    total_pnl=final_capital - self.settings.backtest_initial_capital,
                    total_trades=len(result.trades),
                    metrics=_require_metrics(result),
                    equity_curve=result.equity_curve,
                    run_id=run_model.run_id if run_model is not None else None,
                )
            )
            all_trades.extend(result.trades)

        aggregate = self._build_aggregate_report(symbol_reports, all_trades, resolved_timeframe)
        aggregate_run = self._persist_aggregate_run(
            aggregate,
            symbols=[report.symbol for report in symbol_reports],
            start_date=start_date,
            end_date=end_date,
        )
        if aggregate_run is not None:
            aggregate = BacktestReport(
                symbol=aggregate.symbol,
                timeframe=aggregate.timeframe,
                initial_capital=aggregate.initial_capital,
                final_capital=aggregate.final_capital,
                total_pnl=aggregate.total_pnl,
                total_trades=aggregate.total_trades,
                metrics=aggregate.metrics,
                equity_curve=aggregate.equity_curve,
                run_id=aggregate_run.run_id,
            )
        return MultiSymbolBacktestReport(aggregate=aggregate, symbols=symbol_reports)

    def _run_symbol(
        self,
        symbol: str,
        candles: pd.DataFrame,
        *,
        start_date: str | datetime | None,
        end_date: str | datetime | None,
    ) -> BacktestResult:
        strategy = create_default_strategy_registry().create(self.settings.strategy_name, self.settings)
        engine = BacktestEngine(
            strategy=strategy,
            risk_manager=_create_risk_manager(self.settings),
            initial_capital=self.settings.backtest_initial_capital,
            slippage_bps=self.settings.slippage_bps,
            fee_bps=self.settings.fee_bps,
        )
        return engine.run(candles.copy(), symbol=symbol, start_date=start_date, end_date=end_date)

    def _build_aggregate_report(
        self,
        symbol_reports: list[BacktestReport],
        trades: list[Trade],
        timeframe: str,
    ) -> BacktestReport:
        initial_capital = self.settings.backtest_initial_capital * len(symbol_reports)
        ordered_trades = sorted(trades, key=lambda trade: trade.exit_time)
        equity_curve = [initial_capital]
        for trade in ordered_trades:
            equity_curve.append(equity_curve[-1] + trade.pnl)
        pnls = [trade.pnl for trade in ordered_trades]
        cumulative_returns = [value / initial_capital for value in equity_curve]
        metrics = compute_metrics(pnls, cumulative_returns=cumulative_returns)
        final_capital = equity_curve[-1]
        return BacktestReport(
            symbol="MULTI",
            timeframe=timeframe,
            initial_capital=initial_capital,
            final_capital=final_capital,
            total_pnl=final_capital - initial_capital,
            total_trades=len(ordered_trades),
            metrics=metrics,
            equity_curve=equity_curve,
        )

    def _persist_symbol_run(
        self,
        *,
        symbol: str,
        timeframe: str,
        result: BacktestResult,
        start_date: str | datetime | None,
        end_date: str | datetime | None,
        source: str,
    ) -> BacktestRunModel | None:
        if self.session is None or result.metrics is None:
            return None
        repository = TradeRepository(self.session)
        final_capital = result.equity_curve[-1] if result.equity_curve else self.settings.backtest_initial_capital
        run_model = repository.create_backtest_run(
            strategy_name=self.settings.strategy_name,
            symbol=symbol,
            timeframe=timeframe,
            initial_capital=self.settings.backtest_initial_capital,
            final_capital=final_capital,
            metrics=result.metrics,
            start_date=_coerce_datetime(start_date),
            end_date=_coerce_datetime(end_date),
            config_snapshot={
                "source": source,
                "strategy_name": self.settings.strategy_name,
                "candles": len(result.equity_curve),
            },
        )
        for trade in result.trades:
            repository.create_from_trade(trade, source="backtest")
        return run_model

    def _persist_aggregate_run(
        self,
        aggregate: BacktestReport,
        *,
        symbols: list[str],
        start_date: str | datetime | None,
        end_date: str | datetime | None,
    ) -> BacktestRunModel | None:
        if self.session is None:
            return None
        return TradeRepository(self.session).create_backtest_run(
            strategy_name=self.settings.strategy_name,
            symbol=aggregate.symbol,
            timeframe=aggregate.timeframe,
            initial_capital=aggregate.initial_capital,
            final_capital=aggregate.final_capital,
            metrics=aggregate.metrics,
            start_date=_coerce_datetime(start_date),
            end_date=_coerce_datetime(end_date),
            config_snapshot={
                "source": "multi_symbol_aggregate",
                "symbols": symbols,
                "symbol_count": len(symbols),
            },
        )


class BacktestReportExporter:
    """Write multi-symbol reports to portable JSON or static HTML files."""

    @staticmethod
    def write_json(report: MultiSymbolBacktestReport, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(report.to_dict(), handle, indent=2, allow_nan=False)
            handle.write("\n")
        return path

    @staticmethod
    def write_html(report: MultiSymbolBacktestReport, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        rows = "\n".join(_html_row(symbol_report) for symbol_report in [report.aggregate, *report.symbols])
        document = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>LWK Futures Backtest Report</title>
    <style>
      body {{ font-family: Arial, sans-serif; margin: 32px; color: #111827; }}
      table {{ border-collapse: collapse; width: 100%; }}
      th, td {{ border-bottom: 1px solid #e5e7eb; padding: 10px 12px; text-align: right; }}
      th:first-child, td:first-child {{ text-align: left; }}
      th {{ background: #f3f4f6; }}
    </style>
  </head>
  <body>
    <h1>LWK Futures Backtest Report</h1>
    <p>Generated at {escape(report.generated_at.isoformat())}</p>
    <table>
      <thead>
        <tr>
          <th>Symbol</th>
          <th>Final Capital</th>
          <th>Total PnL</th>
          <th>Trades</th>
          <th>Sharpe</th>
          <th>Sortino</th>
          <th>Max DD %</th>
          <th>Win Rate %</th>
          <th>Profit Factor</th>
          <th>Avg R:R</th>
        </tr>
      </thead>
      <tbody>
        {rows}
      </tbody>
    </table>
  </body>
</html>
"""
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(document)
        return path


def metrics_to_dict(metrics: PerformanceMetrics) -> dict[str, object]:
    return {
        "total_return_pct": _json_number(metrics.total_return_pct),
        "sharpe_ratio": _json_number(metrics.sharpe_ratio),
        "sortino_ratio": _json_number(metrics.sortino_ratio),
        "max_drawdown_pct": _json_number(metrics.max_drawdown_pct),
        "win_rate": _json_number(metrics.win_rate),
        "profit_factor": _json_number(metrics.profit_factor),
        "expectancy": _json_number(metrics.expectancy),
        "total_trades": metrics.total_trades,
        "winning_trades": metrics.winning_trades,
        "losing_trades": metrics.losing_trades,
        "avg_win": _json_number(metrics.avg_win),
        "avg_loss": _json_number(metrics.avg_loss),
        "avg_r_r": _json_number(_avg_risk_reward(metrics)),
    }


def _create_risk_manager(settings: Settings) -> RiskManager:
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


def _require_metrics(result: BacktestResult) -> PerformanceMetrics:
    if result.metrics is None:
        raise ValueError("Backtest metrics were not produced")
    return result.metrics


def _avg_risk_reward(metrics: PerformanceMetrics) -> float | None:
    if metrics.avg_loss >= 0:
        return None
    return float(metrics.avg_win / abs(metrics.avg_loss))


def _json_number(value: float | None) -> float | None:
    if value is None or value != value or value in {float("inf"), float("-inf")}:
        return None
    return value


def _coerce_datetime(value: str | datetime | None) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _html_row(report: BacktestReport) -> str:
    metrics = metrics_to_dict(report.metrics)
    return (
        "<tr>"
        f"<td>{escape(report.symbol)}</td>"
        f"<td>{report.final_capital:.2f}</td>"
        f"<td>{report.total_pnl:.2f}</td>"
        f"<td>{report.total_trades}</td>"
        f"<td>{_format_metric(metrics['sharpe_ratio'])}</td>"
        f"<td>{_format_metric(metrics['sortino_ratio'])}</td>"
        f"<td>{_format_metric(metrics['max_drawdown_pct'])}</td>"
        f"<td>{_format_metric(_percent_metric(metrics['win_rate']))}</td>"
        f"<td>{_format_metric(metrics['profit_factor'])}</td>"
        f"<td>{_format_metric(metrics['avg_r_r'])}</td>"
        "</tr>"
    )


def _percent_metric(value: object) -> float | None:
    if not isinstance(value, float):
        return None
    return value * 100


def _format_metric(value: object) -> str:
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:.2f}"
    return "n/a"
