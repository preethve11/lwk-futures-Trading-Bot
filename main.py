#!/usr/bin/env python3
"""
Trading Bot CLI: backtest | live
Usage:
  python main.py backtest [--config config.yaml]
  python main.py backtest-multi [--config config.yaml]
  python main.py walk-forward [--config config.yaml]
  python main.py monte-carlo [--config config.yaml]
  python main.py strategy-research --trades-csv reports/paper_validation/.../trade_log.csv
  python main.py rejected-signals reports/latest/rejected_signals.json
  python main.py strategy-compare --baseline ema_rsi_vwap --variants ema_rsi_vwap_trend_only
  python main.py db-upgrade [--config config.yaml]
  python main.py db-current [--config config.yaml]
  python main.py mainnet-checklist [--config config.yaml]
  python main.py strategy-gate [--config config.yaml]
  python main.py reconcile-account [--config config.yaml]
  python main.py reconcile-lifecycle [--config config.yaml]
  python main.py recover-unprotected [--config config.yaml]
  python main.py live [--config config.yaml]
  python main.py api [--config config.yaml]
  python main.py market-data [--config config.yaml]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.backtesting.data_loader import load_csv_ohlcv
from app.backtesting.multi_symbol import BacktestReportExporter, MultiSymbolBacktestRunner
from app.backtesting.strategy_compare import StrategyComparisonReportExporter, StrategyComparisonRunner
from app.backtesting.walk_forward import WalkForwardOptimizer, WalkForwardReportExporter
from app.analytics.monte_carlo import MonteCarloReportExporter, MonteCarloSimulator, load_trade_pnls_json
from app.analytics.strategy_research import StrategyResearchReportExporter, analyze_trade_log
from app.core.config import Settings
from app.market_data.binance_ws import BinanceKlineStreamService
from app.market_data.redis_store import RedisKlineStore
from app.ops.mainnet_readiness import evaluate_mainnet_readiness, format_mainnet_readiness_report
from app.ops.performance_gate import evaluate_strategy_performance_gate, format_strategy_performance_gate
from app.persistence.database import create_session_factory, init_db, session_scope
from app.persistence.repositories import TradeRepository
from app.workers.account_equity import AccountEquityReconciliationWorker
from app.workers.exchange_lifecycle import ExchangeLifecycleReconciliationWorker
from app.strategies.registry import create_default_strategy_registry
from app.workers.failed_unprotected_recovery import FailedUnprotectedRecoveryWorker
from app.workers.live_trader import LiveTrader
from trading_bot.backtesting.engine import BacktestArtifactExporter, BacktestEngine, BacktestRecorder, BacktestResult
from trading_bot.core.config import load_config
from trading_bot.core.logger import setup_logging
from trading_bot.execution.binance_futures import BinanceFuturesClient
from trading_bot.risk.manager import RiskManager
from trading_bot.utils.alerts import AlertQueue


def run_backtest(
    config_path: Path | None,
    *,
    symbol: str | None = None,
    timeframe: str | None = None,
    strategy_name: str | None = None,
    start: str | None = None,
    end: str | None = None,
    add_regime_labels: bool = False,
    show_rejected: bool = False,
) -> int:
    """Run backtest using configured strategy, risk, and date range."""
    settings = load_config(config_path, ROOT)
    updates: dict[str, object] = {}
    if symbol is not None:
        updates["symbol"] = symbol.upper()
        updates["symbols"] = [symbol.upper()]
    if timeframe is not None:
        updates["timeframe"] = timeframe
    if strategy_name is not None:
        updates["strategy_name"] = strategy_name
    if start is not None:
        updates["backtest_start"] = start
    if end is not None:
        updates["backtest_end"] = end
    if updates:
        settings = settings.model_copy(update=updates)
    setup_logging(settings.log_level, settings.log_dir, settings.log_file)
    logger = logging.getLogger("trading_bot")

    strategy = create_default_strategy_registry().create(settings.strategy_name, settings)
    risk_manager = RiskManager(
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
    engine = BacktestEngine(
        strategy=strategy,
        risk_manager=risk_manager,
        initial_capital=settings.backtest_initial_capital,
        slippage_bps=settings.slippage_bps,
        fee_bps=settings.fee_bps,
        recorder=_create_backtest_recorder(settings),
        add_regime_labels_to_trades=add_regime_labels,
    )

    if settings.historical_data_csv:
        df = load_csv_ohlcv(
            settings.historical_data_csv,
            start=settings.backtest_start,
            end=settings.backtest_end,
        )
    elif settings.historical_data_dir:
        csv_path = _resolve_symbol_csv(settings.historical_data_dir, settings.symbol, settings.timeframe)
        if csv_path is None:
            logger.error("Missing historical CSV for backtest", extra={"symbol": settings.symbol, "timeframe": settings.timeframe})
            return 1
        df = load_csv_ohlcv(csv_path, start=settings.backtest_start, end=settings.backtest_end)
    else:
        if not settings.active_binance_api_key or not settings.active_binance_api_secret:
            logger.error("Backtest needs Binance API keys or HISTORICAL_DATA_CSV")
            return 1
        client = BinanceFuturesClient(
            settings.active_binance_api_key,
            settings.active_binance_api_secret,
            testnet=settings.use_testnet,
        )
        df = client.get_klines(settings.symbol, settings.timeframe, limit=500)

    result = engine.run(
        df,
        symbol=settings.symbol,
        start_date=settings.backtest_start,
        end_date=settings.backtest_end,
    )
    metrics = result.metrics
    if metrics:
        print("\n--- Backtest Results ---")
        print(f"Total trades: {metrics.total_trades} (wins: {metrics.winning_trades}, losses: {metrics.losing_trades})")
        print(f"Total return: {metrics.total_return_pct:.2f}%")
        print(f"Sharpe ratio: {metrics.sharpe_ratio:.2f}")
        print(f"Sortino ratio: {metrics.sortino_ratio:.2f}")
        print(f"Max drawdown: {metrics.max_drawdown_pct:.2f}%")
        print(f"Win rate: {metrics.win_rate * 100:.1f}%")
        print(f"Profit factor: {metrics.profit_factor:.2f}")
        print(f"Expectancy: {metrics.expectancy:.2f} USD/trade")
    latest_dir = ROOT / "reports" / "latest"
    trade_log_path, rejected_path = BacktestArtifactExporter.write_latest(
        result,
        latest_dir,
        run_name=f"{settings.symbol}_{settings.timeframe}",
        timeframe=settings.timeframe,
    )
    print(f"Trade log: {trade_log_path}")
    print(f"Rejected signals: {rejected_path}")
    if show_rejected:
        _print_rejected_signal_summary(result.rejected_signal_summary())
    return 0


def run_multi_backtest(config_path: Path | None, report_json: Path | None, report_html: Path | None) -> int:
    """Run the configured strategy across all configured symbols and export a report."""
    settings = load_config(config_path, ROOT)
    setup_logging(settings.log_level, settings.log_dir, settings.log_file)
    logger = logging.getLogger("trading_bot")
    datasets = _load_multi_symbol_datasets(settings, logger)
    if not datasets:
        return 1

    session_factory = create_session_factory(settings.database_url)
    try:
        init_db(session_factory)
    except Exception as exc:
        logger.exception("Could not initialize persistence database", extra={"error": str(exc)})

    with session_scope(session_factory) as session:
        report = MultiSymbolBacktestRunner(settings, session).run(
            datasets,
            timeframe=settings.timeframe,
            start_date=settings.backtest_start,
            end_date=settings.backtest_end,
        )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = report_json or settings.backtest_report_dir / f"multi_symbol_{timestamp}.json"
    BacktestReportExporter.write_json(report, json_path)
    if report_html is not None:
        BacktestReportExporter.write_html(report, report_html)

    metrics = report.aggregate.metrics
    print("\n--- Multi-Symbol Backtest Results ---")
    print(f"Symbols: {', '.join(symbol_report.symbol for symbol_report in report.symbols)}")
    print(f"Total trades: {metrics.total_trades}")
    print(f"Total return: {metrics.total_return_pct:.2f}%")
    print(f"Sharpe ratio: {metrics.sharpe_ratio:.2f}")
    print(f"Sortino ratio: {metrics.sortino_ratio:.2f}")
    print(f"Max drawdown: {metrics.max_drawdown_pct:.2f}%")
    print(f"Win rate: {metrics.win_rate * 100:.1f}%")
    print(f"Profit factor: {metrics.profit_factor:.2f}")
    print(f"JSON report: {json_path}")
    if report_html is not None:
        print(f"HTML report: {report_html}")
    return 0


def run_walk_forward(config_path: Path | None, report_json: Path | None) -> int:
    """Run walk-forward strategy optimization and export an out-of-sample report."""
    settings = load_config(config_path, ROOT)
    setup_logging(settings.log_level, settings.log_dir, settings.log_file)
    logger = logging.getLogger("trading_bot")
    candles = _load_walk_forward_dataset(settings, logger)
    if candles is None:
        return 1

    optimizer = WalkForwardOptimizer(
        settings,
        train_size=settings.walk_forward_train_size,
        validation_size=settings.walk_forward_validation_size,
        step_size=settings.walk_forward_step_size,
        n_trials=settings.walk_forward_trials,
        objective=settings.walk_forward_objective,
        random_seed=settings.walk_forward_random_seed,
    )
    report = optimizer.run(candles, symbol=settings.symbol, timeframe=settings.timeframe)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = report_json or settings.walk_forward_report_dir / f"walk_forward_{settings.symbol}_{timestamp}.json"
    WalkForwardReportExporter.write_json(report, json_path)

    metrics = report.aggregate.metrics
    print("\n--- Walk-Forward Optimization Results ---")
    print(f"Symbol: {report.symbol}")
    print(f"Windows: {len(report.windows)}")
    print(f"Trials per window: {report.n_trials}")
    print(f"Objective: {report.objective}")
    print(f"Out-of-sample trades: {metrics.total_trades}")
    print(f"Out-of-sample return: {metrics.total_return_pct:.2f}%")
    print(f"Out-of-sample Sharpe: {metrics.sharpe_ratio:.2f}")
    print(f"Out-of-sample Sortino: {metrics.sortino_ratio:.2f}")
    print(f"Out-of-sample max drawdown: {metrics.max_drawdown_pct:.2f}%")
    print(f"Report: {json_path}")
    return 0


def run_monte_carlo(
    config_path: Path | None,
    returns_json: Path | None,
    report_json: Path | None,
    simulations: int | None,
    horizon_trades: int | None,
    ruin_drawdown_pct: float | None,
) -> int:
    """Run Monte Carlo trade-return simulation and export a risk report."""
    settings = load_config(config_path, ROOT)
    setup_logging(settings.log_level, settings.log_dir, settings.log_file)
    logger = logging.getLogger("trading_bot")
    trade_pnls = _load_monte_carlo_trade_pnls(settings, logger, returns_json)
    if not trade_pnls:
        return 1

    simulator = MonteCarloSimulator(
        initial_capital=settings.backtest_initial_capital,
        simulations=simulations or settings.monte_carlo_simulations,
        horizon_trades=horizon_trades or settings.monte_carlo_horizon_trades,
        ruin_drawdown_pct=ruin_drawdown_pct if ruin_drawdown_pct is not None else settings.monte_carlo_ruin_drawdown_pct,
        random_seed=settings.monte_carlo_random_seed,
    )
    report = simulator.run(trade_pnls)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = report_json or settings.monte_carlo_report_dir / f"monte_carlo_{settings.symbol}_{timestamp}.json"
    MonteCarloReportExporter.write_json(report, json_path)

    print("\n--- Monte Carlo Simulation Results ---")
    print(f"Input trades: {report.input_trade_count}")
    print(f"Simulations: {report.simulations}")
    print(f"Horizon trades: {report.horizon_trades}")
    print(f"Probability of ruin: {report.probability_of_ruin * 100:.2f}%")
    print(f"Final capital p05/p50/p95: {report.final_capital.percentile_5:.2f} / {report.final_capital.percentile_50:.2f} / {report.final_capital.percentile_95:.2f}")
    print(f"Max drawdown p50/p95: {report.max_drawdown_pct.percentile_50:.2f}% / {report.max_drawdown_pct.percentile_95:.2f}%")
    print(f"Report: {json_path}")
    return 0


def run_strategy_research(
    trades_csv: Path | None,
    report_json: Path | None,
    report_markdown: Path | None,
    *,
    rejected_signals_json: Path | None = None,
    group_by_regime: bool = False,
) -> int:
    """Analyze paper-validation trade logs for strategy research diagnostics."""
    source = trades_csv or _latest_trade_log()
    if source is None:
        logging.getLogger("trading_bot.strategy_research").error(
            "strategy-research requires --trades-csv or a reports/paper_validation/*/trade_log.csv artifact"
        )
        return 1
    report = analyze_trade_log(
        source,
        rejected_signals_path=rejected_signals_json,
        group_by_regime=group_by_regime,
    )
    json_path = report_json or source.parent / "strategy_research.json"
    markdown_path = report_markdown or source.parent / "strategy_research.md"
    StrategyResearchReportExporter.write_json(report, json_path)
    StrategyResearchReportExporter.write_markdown(report, markdown_path)

    overview = report.overview
    worst_run = report.question_analysis["worst_run"]
    best_run = report.question_analysis["best_run"]
    print("\n--- Strategy Research Diagnostics ---")
    print(f"Trade log: {source}")
    print(f"Trades: {overview['total_trades']}")
    print(f"Total PnL: {overview['total_pnl']}")
    print(f"Win rate: {float(overview['win_rate']) * 100:.1f}%")
    print(f"Profit factor: {overview['profit_factor']}")
    print(f"Expectancy: {overview['expectancy']} USD/trade")
    print(f"Rejected/executed ratio: {report.rejected_signal_analysis['rejected_to_executed_ratio']}")
    print(f"Worst run: {worst_run['run']}")
    print(f"Best run: {best_run['run']}")
    print(f"Issues: {len(report.issues)}")
    print(f"JSON report: {json_path}")
    print(f"Markdown report: {markdown_path}")
    return 0


def run_rejected_signals(path: Path | None) -> int:
    """Print a rejected-signal JSON breakdown."""
    source = path or ROOT / "reports" / "latest" / "rejected_signals.json"
    if not source.exists():
        logging.getLogger("trading_bot.strategy_research").error(
            "rejected-signals requires a rejected_signals.json path",
            extra={"path": str(source)},
        )
        return 1
    payload = json.loads(source.read_text(encoding="utf-8"))
    _print_rejected_signal_summary(payload)
    return 0


def _print_rejected_signal_summary(payload: dict[str, object]) -> None:
    print("\n--- Rejected Signal Diagnostics ---")
    print(f"Period: {payload.get('period', '')}")
    print(f"Total signals evaluated: {payload.get('total_signals_evaluated', 0)}")
    print(f"Executed trades: {payload.get('executed_trades', 0)}")
    print(f"Rejection rate: {float(payload.get('rejection_rate', 0.0)) * 100:.1f}%")
    rejections = payload.get("rejections", {})
    if isinstance(rejections, dict):
        for reason, count in sorted(rejections.items()):
            print(f"{reason}: {count}")


def run_strategy_compare(
    config_path: Path | None,
    *,
    baseline: str,
    variants: Sequence[str],
    symbols: Sequence[str] | None,
    timeframes: Sequence[str] | None,
    output_dir: Path | None,
) -> int:
    """Compare baseline and strategy variants across local historical datasets."""
    settings = load_config(config_path, ROOT)
    setup_logging(settings.log_level, settings.log_dir, settings.log_file)
    logger = logging.getLogger("trading_bot.strategy_compare")
    selected_symbols = [symbol.upper() for symbol in (symbols or settings.symbols or [settings.symbol])]
    selected_timeframes = list(timeframes or [settings.timeframe])
    datasets = _load_strategy_compare_datasets(settings, selected_symbols, selected_timeframes, logger)
    if not datasets:
        return 1

    report = StrategyComparisonRunner(settings).run(datasets, baseline=baseline, variants=variants)
    target_dir = output_dir or ROOT / "reports" / "strategy_comparison" / "latest"
    json_path = StrategyComparisonReportExporter.write_json(report, target_dir / "strategy_comparison.json")
    markdown_path = StrategyComparisonReportExporter.write_markdown(report, target_dir / "strategy_comparison.md")

    print("\n--- Strategy Comparison ---")
    for row in report.rows:
        profit_factor = f"{row.profit_factor:.2f}" if row.profit_factor is not None else "n/a"
        print(
            f"{row.strategy} {row.symbol}_{row.timeframe}: trades={row.total_trades} "
            f"PF={profit_factor} expectancy={row.expectancy:.2f} rejection={row.rejection_rate * 100:.1f}%"
        )
    if report.winner is not None:
        winner = report.winner
        print(f"Winner: {winner.strategy} on {winner.symbol}_{winner.timeframe}")
    print(f"JSON report: {json_path}")
    print(f"Markdown report: {markdown_path}")
    return 0


def _load_monte_carlo_trade_pnls(
    settings: Settings,
    logger: logging.Logger,
    returns_json: Path | None,
) -> list[float]:
    if returns_json is not None:
        try:
            return load_trade_pnls_json(returns_json, initial_capital=settings.backtest_initial_capital)
        except Exception as exc:
            logger.error("Could not load Monte Carlo returns JSON", extra={"path": str(returns_json), "error": str(exc)})
            return []

    session_factory = create_session_factory(settings.database_url)
    try:
        init_db(session_factory)
        limit = max(settings.monte_carlo_horizon_trades * 10, 100)
        with session_scope(session_factory) as session:
            trades = TradeRepository(session).list_recent(symbol=settings.symbol, limit=limit)
            return [trade.pnl for trade in trades]
    except Exception as exc:
        logger.error("Could not load persisted trades for Monte Carlo simulation", extra={"error": str(exc)})
        return []


def _latest_trade_log() -> Path | None:
    candidates = list((ROOT / "reports" / "paper_validation").glob("*/trade_log.csv"))
    latest = ROOT / "reports" / "latest" / "trade_log.csv"
    if latest.exists():
        candidates.append(latest)
    candidates = sorted(candidates, key=lambda path: path.stat().st_mtime)
    return candidates[-1] if candidates else None


def _load_walk_forward_dataset(settings: Settings, logger: logging.Logger) -> pd.DataFrame | None:
    if settings.historical_data_csv is not None:
        return load_csv_ohlcv(
            settings.historical_data_csv,
            start=settings.backtest_start,
            end=settings.backtest_end,
        )

    if settings.historical_data_dir is not None:
        csv_path = _resolve_symbol_csv(settings.historical_data_dir, settings.symbol, settings.timeframe)
        if csv_path is None:
            logger.error("Missing historical CSV for walk-forward symbol", extra={"symbol": settings.symbol})
            return None
        return load_csv_ohlcv(csv_path, start=settings.backtest_start, end=settings.backtest_end)

    if not settings.active_binance_api_key or not settings.active_binance_api_secret:
        logger.error("Walk-forward optimization needs Binance API keys, HISTORICAL_DATA_CSV, or HISTORICAL_DATA_DIR")
        return None

    client = BinanceFuturesClient(
        settings.active_binance_api_key,
        settings.active_binance_api_secret,
        testnet=settings.use_testnet,
    )
    required = settings.walk_forward_train_size + settings.walk_forward_validation_size
    limit = min(1500, max(required + settings.walk_forward_step_size * 4, required))
    return client.get_klines(settings.symbol, settings.timeframe, limit=limit)


def _load_multi_symbol_datasets(settings: Settings, logger: logging.Logger) -> dict[str, pd.DataFrame]:
    symbols = settings.symbols or [settings.symbol]
    if settings.historical_data_dir is not None:
        datasets = {}
        for symbol in symbols:
            csv_path = _resolve_symbol_csv(settings.historical_data_dir, symbol, settings.timeframe)
            if csv_path is None:
                logger.error("Missing historical CSV for symbol", extra={"symbol": symbol})
                return {}
            datasets[symbol] = load_csv_ohlcv(csv_path, start=settings.backtest_start, end=settings.backtest_end)
        return datasets

    if settings.historical_data_csv is not None:
        if len(symbols) != 1:
            logger.error("HISTORICAL_DATA_DIR is required when backtesting multiple symbols from CSV files")
            return {}
        return {symbols[0]: load_csv_ohlcv(settings.historical_data_csv, start=settings.backtest_start, end=settings.backtest_end)}

    if not settings.active_binance_api_key or not settings.active_binance_api_secret:
        logger.error("Multi-symbol backtest needs Binance API keys or HISTORICAL_DATA_DIR")
        return {}

    client = BinanceFuturesClient(
        settings.active_binance_api_key,
        settings.active_binance_api_secret,
        testnet=settings.use_testnet,
    )
    return {symbol: client.get_klines(symbol, settings.timeframe, limit=500) for symbol in symbols}


def _load_strategy_compare_datasets(
    settings: Settings,
    symbols: Sequence[str],
    timeframes: Sequence[str],
    logger: logging.Logger,
) -> dict[tuple[str, str], pd.DataFrame]:
    directories = [directory for directory in [settings.historical_data_dir, _latest_paper_validation_data_dir()] if directory is not None]
    datasets: dict[tuple[str, str], pd.DataFrame] = {}
    for symbol in symbols:
        for timeframe in timeframes:
            csv_path = _resolve_first_symbol_csv(directories, symbol, timeframe)
            if csv_path is None:
                logger.error(
                    "Missing historical CSV for strategy comparison",
                    extra={"symbol": symbol, "timeframe": timeframe},
                )
                return {}
            datasets[(symbol, timeframe)] = load_csv_ohlcv(
                csv_path,
                start=settings.backtest_start,
                end=settings.backtest_end,
            )
    return datasets


def _resolve_first_symbol_csv(directories: Sequence[Path], symbol: str, timeframe: str) -> Path | None:
    for directory in directories:
        csv_path = _resolve_symbol_csv(directory, symbol, timeframe)
        if csv_path is not None:
            return csv_path
    return None


def _latest_paper_validation_data_dir() -> Path | None:
    root = ROOT / "reports" / "paper_validation"
    candidates = sorted(root.glob("*/data"), key=lambda path: path.stat().st_mtime)
    return candidates[-1] if candidates else None


def _resolve_symbol_csv(directory: Path, symbol: str, timeframe: str) -> Path | None:
    candidates = [
        directory / f"{symbol}_{timeframe}.csv",
        directory / f"{symbol.lower()}_{timeframe}.csv",
        directory / f"{symbol}.csv",
        directory / f"{symbol.lower()}.csv",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _create_backtest_recorder(settings: Settings) -> BacktestRecorder:
    """Create a best-effort persistence recorder for backtest results."""
    session_factory = create_session_factory(settings.database_url)
    try:
        init_db(session_factory)
    except Exception as exc:
        logging.getLogger("trading_bot").exception("Could not initialize persistence database", extra={"error": str(exc)})

    def record(
        result: BacktestResult,
        symbol: str,
        start_date: str | datetime | None,
        end_date: str | datetime | None,
    ) -> None:
        if result.metrics is None:
            return
        try:
            with session_scope(session_factory) as session:
                repository = TradeRepository(session)
                final_capital = result.equity_curve[-1] if result.equity_curve else settings.backtest_initial_capital
                repository.create_backtest_run(
                    strategy_name=settings.strategy_name,
                    symbol=symbol,
                    timeframe=settings.timeframe,
                    initial_capital=settings.backtest_initial_capital,
                    final_capital=final_capital,
                    metrics=result.metrics,
                    start_date=_coerce_datetime(start_date),
                    end_date=_coerce_datetime(end_date),
                    config_snapshot={
                        "start_date": str(start_date) if start_date is not None else None,
                        "end_date": str(end_date) if end_date is not None else None,
                    },
                )
                for trade in result.trades:
                    repository.create_from_trade(trade, source="backtest")
        except Exception as exc:
            logging.getLogger("trading_bot").exception("Could not persist backtest run", extra={"error": str(exc)})

    return record


def _coerce_datetime(value: str | datetime | None) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def run_live(config_path: Path | None) -> int:
    """Run live trading loop through the worker layer."""
    settings = load_config(config_path, ROOT)
    setup_logging(settings.log_level, settings.log_dir, settings.log_file)
    return LiveTrader(settings).run_forever()


def run_market_data(config_path: Path | None, max_messages: int | None) -> int:
    """Run Binance kline WebSocket ingestion into Redis."""
    settings = load_config(config_path, ROOT)
    setup_logging(settings.log_level, settings.log_dir, settings.log_file)
    return asyncio.run(_run_market_data_async(settings, max_messages=max_messages))


def run_db_upgrade(config_path: Path | None, revision: str) -> int:
    """Run Alembic migrations to the requested revision."""
    from alembic import command

    settings = load_config(config_path, ROOT)
    setup_logging(settings.log_level, settings.log_dir, settings.log_file)
    command.upgrade(_alembic_config(settings.database_url), revision)
    return 0


def run_db_current(config_path: Path | None) -> int:
    """Print the current Alembic database revision."""
    from alembic import command

    settings = load_config(config_path, ROOT)
    setup_logging(settings.log_level, settings.log_dir, settings.log_file)
    command.current(_alembic_config(settings.database_url), verbose=True)
    return 0


def run_mainnet_checklist(config_path: Path | None, small_notional_usd: float, allow_failures: bool) -> int:
    """Run read-only mainnet readiness checks without exchange calls."""
    settings = load_config(config_path, ROOT)
    setup_logging(settings.log_level, settings.log_dir, settings.log_file)
    report = evaluate_mainnet_readiness(settings, small_notional_usd=small_notional_usd)
    print(format_mainnet_readiness_report(report))
    return 0 if report.ready or allow_failures else 1


def run_strategy_gate(config_path: Path | None, allow_failures: bool) -> int:
    """Evaluate the latest persisted backtest against live promotion thresholds."""
    settings = load_config(config_path, ROOT)
    setup_logging(settings.log_level, settings.log_dir, settings.log_file)
    session_factory = create_session_factory(settings.database_url)
    try:
        init_db(session_factory)
    except Exception as exc:
        logging.getLogger("trading_bot.strategy_gate").exception(
            "Could not initialize persistence database",
            extra={"error": str(exc)},
        )
    with session_scope(session_factory) as session:
        result = evaluate_strategy_performance_gate(session, settings)
    print(format_strategy_performance_gate(result))
    return 0 if result.allowed or allow_failures else 1


def run_recover_unprotected(config_path: Path | None, limit: int) -> int:
    """Recover persisted failed-unprotected orders with verification and emergency close."""
    settings = load_config(config_path, ROOT)
    setup_logging(settings.log_level, settings.log_dir, settings.log_file)
    logger = logging.getLogger("trading_bot.failed_unprotected_recovery")
    if not settings.active_binance_api_key or not settings.active_binance_api_secret:
        logger.error("Recovery needs active Binance API keys")
        return 1

    session_factory = create_session_factory(settings.database_url)
    try:
        init_db(session_factory)
    except Exception as exc:
        logger.exception("Could not initialize persistence database", extra={"error": str(exc)})

    alert_queue = AlertQueue(
        bot_token=settings.telegram_bot_token,
        chat_id=settings.telegram_chat_id,
    )
    try:
        worker = FailedUnprotectedRecoveryWorker(
            session_factory=session_factory,
            client=BinanceFuturesClient(
                settings.active_binance_api_key,
                settings.active_binance_api_secret,
                testnet=settings.use_testnet,
            ),
            alert_queue=alert_queue,
        )
        summary = worker.recover_once(limit=limit)
        print("\n--- Failed Unprotected Recovery ---")
        print(f"Scanned: {summary.scanned}")
        print(f"Recovered protection: {summary.recovered}")
        print(f"Emergency closed: {summary.emergency_closed}")
        print(f"Manual review: {summary.manual_review}")
        print(f"Errors: {len(summary.errors)}")
        return 1 if summary.errors else 0
    finally:
        alert_queue.stop(drain=True)


def run_reconcile_lifecycle(config_path: Path | None, limit: int) -> int:
    """Run one exchange lifecycle reconciliation sweep."""
    settings = load_config(config_path, ROOT)
    setup_logging(settings.log_level, settings.log_dir, settings.log_file)
    logger = logging.getLogger("trading_bot.exchange_lifecycle")
    if not settings.active_binance_api_key or not settings.active_binance_api_secret:
        logger.error("Lifecycle reconciliation needs active Binance API keys")
        return 1

    session_factory = create_session_factory(settings.database_url)
    try:
        init_db(session_factory)
    except Exception as exc:
        logger.exception("Could not initialize persistence database", extra={"error": str(exc)})

    alert_queue = AlertQueue(
        bot_token=settings.telegram_bot_token,
        chat_id=settings.telegram_chat_id,
    )
    try:
        worker = ExchangeLifecycleReconciliationWorker(
            session_factory=session_factory,
            client=BinanceFuturesClient(
                settings.active_binance_api_key,
                settings.active_binance_api_secret,
                testnet=settings.use_testnet,
            ),
            alert_queue=alert_queue,
        )
        summary = worker.reconcile_once(symbols=settings.symbols or [settings.symbol], order_limit=limit)
        print("\n--- Exchange Lifecycle Reconciliation ---")
        print(f"Orders polled: {summary.orders_polled}")
        print(f"Orders updated: {summary.orders_updated}")
        print(f"Missing statuses: {summary.missing_order_statuses}")
        print(f"Terminal order events: {summary.terminal_order_events}")
        print(f"Positions synced: {summary.positions_synced}")
        print(f"Drift events: {summary.drift_events}")
        print(f"Stale reduce-only orders cancelled: {summary.stale_orders_cancelled}")
        print(f"Cancel failures: {summary.cancel_failures}")
        print(f"Errors: {len(summary.errors)}")
        return 1 if summary.errors or summary.cancel_failures else 0
    finally:
        alert_queue.stop(drain=True)


def run_reconcile_account(config_path: Path | None, asset: str) -> int:
    """Run one live account wallet/equity reconciliation sweep."""
    settings = load_config(config_path, ROOT)
    setup_logging(settings.log_level, settings.log_dir, settings.log_file)
    logger = logging.getLogger("trading_bot.account_equity")
    if not settings.active_binance_api_key or not settings.active_binance_api_secret:
        logger.error("Account reconciliation needs active Binance API keys")
        return 1

    session_factory = create_session_factory(settings.database_url)
    try:
        init_db(session_factory)
    except Exception as exc:
        logger.exception("Could not initialize persistence database", extra={"error": str(exc)})

    alert_queue = AlertQueue(
        bot_token=settings.telegram_bot_token,
        chat_id=settings.telegram_chat_id,
    )
    try:
        worker = AccountEquityReconciliationWorker(
            session_factory=session_factory,
            client=BinanceFuturesClient(
                settings.active_binance_api_key,
                settings.active_binance_api_secret,
                testnet=settings.use_testnet,
            ),
            alert_queue=alert_queue,
            drift_threshold_usd=settings.account_equity_drift_threshold_usd,
            drift_threshold_pct=settings.account_equity_drift_threshold_pct,
        )
        summary = worker.reconcile_once(asset=asset)
        print("\n--- Account Equity Reconciliation ---")
        print(f"Asset: {summary.asset}")
        print(f"Snapshot ID: {summary.snapshot_id}")
        print(f"Previous equity: {summary.previous_equity}")
        print(f"Current equity: {summary.current_equity}")
        print(f"Equity delta: {summary.equity_delta}")
        print(f"Equity delta pct: {summary.equity_delta_pct}")
        print(f"Wallet delta: {summary.wallet_delta}")
        print(f"Drift detected: {summary.drift_detected}")
        print(f"Errors: {len(summary.errors)}")
        return 1 if summary.errors else 0
    finally:
        alert_queue.stop(drain=True)


def _alembic_config(database_url: str):
    from alembic.config import Config as AlembicConfig

    config = AlembicConfig(str(ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


async def _run_market_data_async(settings: Settings, max_messages: int | None) -> int:
    from redis.asyncio import Redis

    redis_client = Redis.from_url(settings.redis_url)
    try:
        service = BinanceKlineStreamService(
            symbols=settings.symbols or [settings.symbol],
            interval=settings.timeframe,
            redis_client=redis_client,
            store=RedisKlineStore(history_size=settings.market_data_history_size),
            testnet=settings.use_testnet,
            base_channel=settings.market_data_channel,
            reconnect_backoff_seconds=settings.market_data_reconnect_backoff_seconds,
        )
        published = await service.run(max_messages=max_messages)
        logging.getLogger("trading_bot.market_data").info("Market data service stopped", extra={"published": published})
        return 0
    finally:
        await redis_client.aclose()


def main() -> int:
    parser = argparse.ArgumentParser(description="Trading Bot CLI")
    parser.add_argument(
        "mode",
        choices=[
            "backtest",
            "backtest-multi",
            "walk-forward",
            "monte-carlo",
            "strategy-research",
            "rejected-signals",
            "strategy-compare",
            "db-upgrade",
            "db-current",
            "mainnet-checklist",
            "strategy-gate",
            "reconcile-account",
            "reconcile-lifecycle",
            "recover-unprotected",
            "live",
            "api",
            "market-data",
        ],
        help=(
            "Run backtest, backtest-multi, walk-forward, monte-carlo, strategy-research, rejected-signals, "
            "strategy-compare, db-upgrade, db-current, "
            "mainnet-checklist, strategy-gate, reconcile-account, reconcile-lifecycle, recover-unprotected, live, api, or market-data"
        ),
    )
    parser.add_argument("paths", nargs="*", type=Path, help="Optional positional artifact paths for selected modes")
    parser.add_argument("--config", type=Path, default=None, help="Path to config.yaml")
    parser.add_argument("--host", default="127.0.0.1", help="API host")
    parser.add_argument("--port", type=int, default=8000, help="API port")
    parser.add_argument("--report-json", type=Path, default=None, help="JSON report output path")
    parser.add_argument("--report-html", type=Path, default=None, help="Optional multi-symbol HTML report path")
    parser.add_argument("--max-messages", type=int, default=None, help="Stop market-data mode after N published messages")
    parser.add_argument("--returns-json", type=Path, default=None, help="Monte Carlo input JSON with pnls, returns, or equity_curve")
    parser.add_argument("--trades-csv", type=Path, default=None, help="Trade log CSV for strategy-research mode")
    parser.add_argument("--rejected-signals-json", type=Path, default=None, help="Rejected signals JSON for strategy-research")
    parser.add_argument("--report-markdown", type=Path, default=None, help="Markdown strategy research report output path")
    parser.add_argument("--symbol", default=None, help="Override single symbol")
    parser.add_argument("--symbols", nargs="*", default=None, help="Symbols for strategy-compare")
    parser.add_argument("--timeframe", default=None, help="Override single timeframe")
    parser.add_argument("--timeframes", nargs="*", default=None, help="Timeframes for strategy-compare")
    parser.add_argument("--strategy", default=None, help="Override strategy name for backtest")
    parser.add_argument("--baseline", default="ema_rsi_vwap", help="Baseline strategy for strategy-compare")
    parser.add_argument("--variants", nargs="*", default=[], help="Strategy variants for strategy-compare")
    parser.add_argument("--output-dir", type=Path, default=None, help="Output directory for generated reports")
    parser.add_argument("--start", default=None, help="Backtest start date override")
    parser.add_argument("--end", default=None, help="Backtest end date override")
    parser.add_argument("--add-regime-labels", action="store_true", help="Add regime labels to backtest trade log")
    parser.add_argument("--show-rejected", action="store_true", help="Print rejected-signal breakdown after backtest")
    parser.add_argument("--group-by-regime", action="store_true", help="Add regime breakdown to strategy-research")
    parser.add_argument("--simulations", type=int, default=None, help="Monte Carlo simulation count")
    parser.add_argument("--horizon-trades", type=int, default=None, help="Monte Carlo forward trade horizon")
    parser.add_argument("--ruin-drawdown-pct", type=float, default=None, help="Monte Carlo ruin threshold as drawdown percent")
    parser.add_argument("--revision", default="head", help="Alembic revision for db-upgrade")
    parser.add_argument("--limit", type=int, default=100, help="Maximum failed-unprotected orders to recover")
    parser.add_argument("--asset", default="USDT", help="Account asset for account reconciliation")
    parser.add_argument("--small-notional-usd", type=float, default=10.0, help="Risk budget for mainnet checklist")
    parser.add_argument("--allow-failures", action="store_true", help="Return zero even when checklist items fail")
    args = parser.parse_args()
    if args.mode == "backtest":
        return run_backtest(
            args.config,
            symbol=args.symbol,
            timeframe=args.timeframe,
            strategy_name=args.strategy,
            start=args.start,
            end=args.end,
            add_regime_labels=args.add_regime_labels,
            show_rejected=args.show_rejected,
        )
    if args.mode == "backtest-multi":
        return run_multi_backtest(args.config, args.report_json, args.report_html)
    if args.mode == "walk-forward":
        return run_walk_forward(args.config, args.report_json)
    if args.mode == "monte-carlo":
        return run_monte_carlo(
            args.config,
            args.returns_json,
            args.report_json,
            args.simulations,
            args.horizon_trades,
            args.ruin_drawdown_pct,
        )
    if args.mode == "strategy-research":
        trades_csv = args.trades_csv or (args.paths[0] if args.paths else None)
        return run_strategy_research(
            trades_csv,
            args.report_json,
            args.report_markdown,
            rejected_signals_json=args.rejected_signals_json,
            group_by_regime=args.group_by_regime,
        )
    if args.mode == "rejected-signals":
        return run_rejected_signals(args.paths[0] if args.paths else None)
    if args.mode == "strategy-compare":
        return run_strategy_compare(
            args.config,
            baseline=args.baseline,
            variants=args.variants,
            symbols=args.symbols,
            timeframes=args.timeframes,
            output_dir=args.output_dir,
        )
    if args.mode == "db-upgrade":
        return run_db_upgrade(args.config, args.revision)
    if args.mode == "db-current":
        return run_db_current(args.config)
    if args.mode == "mainnet-checklist":
        return run_mainnet_checklist(args.config, args.small_notional_usd, args.allow_failures)
    if args.mode == "strategy-gate":
        return run_strategy_gate(args.config, args.allow_failures)
    if args.mode == "reconcile-account":
        return run_reconcile_account(args.config, args.asset)
    if args.mode == "reconcile-lifecycle":
        return run_reconcile_lifecycle(args.config, args.limit)
    if args.mode == "recover-unprotected":
        return run_recover_unprotected(args.config, args.limit)
    if args.mode == "api":
        import uvicorn

        settings = load_config(args.config, ROOT)
        setup_logging(settings.log_level, settings.log_dir, settings.log_file)
        uvicorn.run("app.api.main:app", host=args.host, port=args.port, reload=False)
        return 0
    if args.mode == "market-data":
        return run_market_data(args.config, args.max_messages)
    return run_live(args.config)


if __name__ == "__main__":
    raise SystemExit(main())
