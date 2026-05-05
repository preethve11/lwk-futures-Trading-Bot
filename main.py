#!/usr/bin/env python3
"""
Trading Bot CLI: backtest | live
Usage:
  python main.py backtest [--config config.yaml]
  python main.py live [--config config.yaml]
  python main.py api [--config config.yaml]
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.backtesting.data_loader import load_csv_ohlcv
from app.core.config import Settings
from app.persistence.database import create_session_factory, init_db, session_scope
from app.persistence.repositories import TradeRepository
from app.strategies.registry import create_default_strategy_registry
from app.workers.live_trader import LiveTrader
from trading_bot.backtesting.engine import BacktestEngine, BacktestRecorder, BacktestResult
from trading_bot.core.config import load_config
from trading_bot.core.logger import setup_logging
from trading_bot.execution.binance_futures import BinanceFuturesClient
from trading_bot.risk.manager import RiskManager


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


def main() -> int:
    parser = argparse.ArgumentParser(description="Trading Bot CLI")
    parser.add_argument("mode", choices=["backtest", "live", "api"], help="Run backtest, live, or api")
    parser.add_argument("--config", type=Path, default=None, help="Path to config.yaml")
    parser.add_argument("--host", default="127.0.0.1", help="API host")
    parser.add_argument("--port", type=int, default=8000, help="API port")
    args = parser.parse_args()
    if args.mode == "backtest":
        return run_backtest(args.config)
    if args.mode == "api":
        import uvicorn

        settings = load_config(args.config, ROOT)
        setup_logging(settings.log_level, settings.log_dir, settings.log_file)
        uvicorn.run("app.api.main:app", host=args.host, port=args.port, reload=False)
        return 0
    return run_live(args.config)


if __name__ == "__main__":
    raise SystemExit(main())
