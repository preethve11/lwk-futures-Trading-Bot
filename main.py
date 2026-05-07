#!/usr/bin/env python3
"""
Trading Bot CLI: backtest | live
Usage:
  python main.py backtest [--config config.yaml]
  python main.py backtest-multi [--config config.yaml]
  python main.py walk-forward [--config config.yaml]
  python main.py monte-carlo [--config config.yaml]
  python main.py db-upgrade [--config config.yaml]
  python main.py db-current [--config config.yaml]
  python main.py mainnet-checklist [--config config.yaml]
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
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.backtesting.data_loader import load_csv_ohlcv
from app.backtesting.multi_symbol import BacktestReportExporter, MultiSymbolBacktestRunner
from app.backtesting.walk_forward import WalkForwardOptimizer, WalkForwardReportExporter
from app.analytics.monte_carlo import MonteCarloReportExporter, MonteCarloSimulator, load_trade_pnls_json
from app.core.config import Settings
from app.market_data.binance_ws import BinanceKlineStreamService
from app.market_data.redis_store import RedisKlineStore
from app.ops.mainnet_readiness import evaluate_mainnet_readiness, format_mainnet_readiness_report
from app.persistence.database import create_session_factory, init_db, session_scope
from app.persistence.repositories import TradeRepository
from app.workers.account_equity import AccountEquityReconciliationWorker
from app.workers.exchange_lifecycle import ExchangeLifecycleReconciliationWorker
from app.strategies.registry import create_default_strategy_registry
from app.workers.failed_unprotected_recovery import FailedUnprotectedRecoveryWorker
from app.workers.live_trader import LiveTrader
from trading_bot.backtesting.engine import BacktestEngine, BacktestRecorder, BacktestResult
from trading_bot.core.config import load_config
from trading_bot.core.logger import setup_logging
from trading_bot.execution.binance_futures import BinanceFuturesClient
from trading_bot.risk.manager import RiskManager
from trading_bot.utils.alerts import AlertQueue


def run_backtest(config_path: Path | None) -> int:
    """Run backtest using configured strategy, risk, and date range."""
    settings = load_config(config_path, ROOT)
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
    )

    if settings.historical_data_csv:
        df = load_csv_ohlcv(
            settings.historical_data_csv,
            start=settings.backtest_start,
            end=settings.backtest_end,
        )
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
            "db-upgrade",
            "db-current",
            "mainnet-checklist",
            "reconcile-account",
            "reconcile-lifecycle",
            "recover-unprotected",
            "live",
            "api",
            "market-data",
        ],
        help=(
            "Run backtest, backtest-multi, walk-forward, monte-carlo, db-upgrade, db-current, "
            "mainnet-checklist, reconcile-account, reconcile-lifecycle, recover-unprotected, live, api, or market-data"
        ),
    )
    parser.add_argument("--config", type=Path, default=None, help="Path to config.yaml")
    parser.add_argument("--host", default="127.0.0.1", help="API host")
    parser.add_argument("--port", type=int, default=8000, help="API port")
    parser.add_argument("--report-json", type=Path, default=None, help="JSON report output path")
    parser.add_argument("--report-html", type=Path, default=None, help="Optional multi-symbol HTML report path")
    parser.add_argument("--max-messages", type=int, default=None, help="Stop market-data mode after N published messages")
    parser.add_argument("--returns-json", type=Path, default=None, help="Monte Carlo input JSON with pnls, returns, or equity_curve")
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
        return run_backtest(args.config)
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
    if args.mode == "db-upgrade":
        return run_db_upgrade(args.config, args.revision)
    if args.mode == "db-current":
        return run_db_current(args.config)
    if args.mode == "mainnet-checklist":
        return run_mainnet_checklist(args.config, args.small_notional_usd, args.allow_failures)
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
