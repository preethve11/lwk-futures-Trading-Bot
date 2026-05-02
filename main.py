#!/usr/bin/env python3
"""
Trading Bot CLI: backtest | live
Usage:
  python main.py backtest [--config config.yaml]
  python main.py live [--config config.yaml]
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.backtesting.data_loader import load_csv_ohlcv
from app.strategies.registry import create_default_strategy_registry
from app.workers.live_trader import LiveTrader
from trading_bot.backtesting.engine import BacktestEngine
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


def run_live(config_path: Path | None) -> int:
    """Run live trading loop through the worker layer."""
    settings = load_config(config_path, ROOT)
    setup_logging(settings.log_level, settings.log_dir, settings.log_file)
    return LiveTrader(settings).run_forever()


def main() -> int:
    parser = argparse.ArgumentParser(description="Trading Bot CLI")
    parser.add_argument("mode", choices=["backtest", "live"], help="Run backtest or live")
    parser.add_argument("--config", type=Path, default=None, help="Path to config.yaml")
    args = parser.parse_args()
    if args.mode == "backtest":
        return run_backtest(args.config)
    return run_live(args.config)


if __name__ == "__main__":
    raise SystemExit(main())
