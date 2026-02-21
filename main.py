#!/usr/bin/env python3
"""
Trading Bot CLI: backtest | live
Usage:
  python main.py backtest [--config config.yaml]
  python main.py live [--config config.yaml]
"""

from __future__ import annotations
import argparse
import sys
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta

import pandas as pd

# Project root
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trading_bot.core.config import load_config
from trading_bot.core.logger import setup_logging
from trading_bot.strategies.ema_rsi_vwap import EmaRsiVwapStrategy
from trading_bot.risk.manager import RiskManager
from trading_bot.execution.binance_futures import BinanceFuturesClient
from trading_bot.backtesting.engine import BacktestEngine
from trading_bot.utils.telegram import send_telegram
from trading_bot.utils.timeframes import timeframe_minutes


def run_backtest(config_path: Path | None) -> int:
    """Run backtest using config and optional date range."""
    config = load_config(config_path, ROOT)
    setup_logging(config.log_level, config.log_dir, config.log_file)
    logger = __import__("logging").getLogger("trading_bot")
    # Strategy
    strategy = EmaRsiVwapStrategy(
        ema_fast=config.ema_fast,
        ema_slow=config.ema_slow,
        rsi_len=config.rsi_len,
        atr_len=config.atr_len,
        atr_stop_mult=config.atr_stop_mult,
        atr_tp_mult=config.atr_tp_mult,
        vol_mult=config.vol_mult,
        vol_ma_len=config.vol_ma_len,
        rsi_long_min=config.rsi_long_min,
        rsi_short_max=config.rsi_short_max,
        cooldown_candles=config.cooldown_candles,
    )
    risk_manager = RiskManager(
        risk_per_trade_usd=config.risk_per_trade_usd,
        max_daily_loss_usd=config.max_daily_loss_usd,
        max_drawdown_pct=config.max_drawdown_pct,
        min_notional=config.min_notional,
        max_position_pct_capital=config.max_position_pct_capital,
        min_risk_reward=config.min_risk_reward,
        use_atr_position_cap=config.use_atr_position_cap,
        trailing_stop_atr_mult=config.trailing_stop_atr_mult,
        symbol_info=None,
    )
    engine = BacktestEngine(
        strategy=strategy,
        risk_manager=risk_manager,
        initial_capital=config.backtest_initial_capital,
        slippage_bps=config.slippage_bps,
        fee_bps=config.fee_bps,
    )
    # Get data: use Binance client for historical klines (or load CSV if you add it)
    if not config.binance_api_key or not config.binance_api_secret:
        logger.error("Backtest needs API keys to fetch klines. Set BINANCE_API_KEY and BINANCE_API_SECRET in .env")
        return 1
    client = BinanceFuturesClient(
        config.binance_api_key,
        config.binance_api_secret,
        testnet=config.use_testnet,
    )
    limit = 500
    df = client.get_klines(config.symbol, config.timeframe, limit=limit)
    result = engine.run(df, symbol=config.symbol)
    # Print metrics
    m = result.metrics
    if m:
        print("\n--- Backtest Results ---")
        print(f"Total trades: {m.total_trades} (wins: {m.winning_trades}, losses: {m.losing_trades})")
        print(f"Total return: {m.total_return_pct:.2f}%")
        print(f"Sharpe ratio: {m.sharpe_ratio:.2f}")
        print(f"Sortino ratio: {m.sortino_ratio:.2f}")
        print(f"Max drawdown: {m.max_drawdown_pct:.2f}%")
        print(f"Win rate: {m.win_rate*100:.1f}%")
        print(f"Profit factor: {m.profit_factor:.2f}")
        print(f"Expectancy: {m.expectancy:.2f} USD/trade")
    return 0


def run_live(config_path: Path | None) -> int:
    """Run live trading loop."""
    config = load_config(config_path, ROOT)
    setup_logging(config.log_level, config.log_dir, config.log_file)
    logger = __import__("logging").getLogger("trading_bot")
    if not config.binance_api_key or not config.binance_api_secret:
        logger.error("Missing BINANCE_API_KEY or BINANCE_API_SECRET in .env")
        return 1
    client = BinanceFuturesClient(
        config.binance_api_key,
        config.binance_api_secret,
        testnet=config.use_testnet,
    )
    client.set_leverage(config.symbol, config.leverage)
    symbol_info = client.get_symbol_info(config.symbol)
    risk_manager = RiskManager(
        risk_per_trade_usd=config.risk_per_trade_usd,
        max_daily_loss_usd=config.max_daily_loss_usd,
        max_drawdown_pct=config.max_drawdown_pct,
        min_notional=config.min_notional,
        max_position_pct_capital=config.max_position_pct_capital,
        min_risk_reward=config.min_risk_reward,
        use_atr_position_cap=config.use_atr_position_cap,
        trailing_stop_atr_mult=config.trailing_stop_atr_mult,
        symbol_info=symbol_info,
    )
    strategy = EmaRsiVwapStrategy(
        ema_fast=config.ema_fast,
        ema_slow=config.ema_slow,
        rsi_len=config.rsi_len,
        atr_len=config.atr_len,
        atr_stop_mult=config.atr_stop_mult,
        atr_tp_mult=config.atr_tp_mult,
        vol_mult=config.vol_mult,
        vol_ma_len=config.vol_ma_len,
        rsi_long_min=config.rsi_long_min,
        rsi_short_max=config.rsi_short_max,
        cooldown_candles=config.cooldown_candles,
    )
    cooldown_s = timeframe_minutes(config.timeframe) * 60
    last_signal_ts = 0.0
    last_hourly = datetime.now(timezone.utc)
    send_telegram(
        f"Trading bot starting | {config.symbol} | testnet={config.use_testnet} | leverage={config.leverage}x",
        config.telegram_bot_token,
        config.telegram_chat_id,
    )
    while True:
        try:
            # Daily loss from exchange
            trades = client.fetch_recent_trades(config.symbol, limit=500)
            now_date = datetime.now(timezone.utc).date()
            day_start_ts = int(datetime.combine(now_date, datetime.min.time(), tzinfo=timezone.utc).timestamp() * 1000)
            realized = sum(float(t.get("realizedPnl", 0)) for t in trades if int(t.get("time", 0)) >= day_start_ts)
            daily_loss = max(0.0, -realized)
            risk_manager.set_daily_loss(daily_loss, now_date)
            if not risk_manager.check_daily_loss():
                logger.warning("Daily loss cap reached")
                time.sleep(60)
                continue
            pos = client.get_open_position(config.symbol)
            if pos and pos.quantity > 0:
                logger.info("Position open, waiting...")
                time.sleep(5)
                # Hourly summary
                if (datetime.now(timezone.utc) - last_hourly) >= timedelta(minutes=55):
                    msg = f"Hourly | {config.symbol} | Open pos: {pos.quantity} @ {pos.entry_price} | Daily loss: ${daily_loss:.2f}"
                    send_telegram(msg, config.telegram_bot_token, config.telegram_chat_id)
                    last_hourly = datetime.now(timezone.utc)
                continue
            if time.time() - last_signal_ts < cooldown_s:
                time.sleep(1)
                continue
            df = client.get_klines(config.symbol, config.timeframe, limit=300)
            df = strategy.compute_indicators(df)
            raw = strategy.get_signal(df)
            if raw is None:
                time.sleep(1)
                continue
            prev = df.iloc[-2]
            atr = float(prev["atr"]) if not pd.isna(prev.get("atr")) else 0.0
            result = risk_manager.validate_signal(
                raw.entry_price, raw.stop_price, raw.take_profit_price,
                raw.side, atr, None,
            )
            if not result.allowed or result.quantity <= 0:
                time.sleep(1)
                continue
            from trading_bot.core.types import Signal
            signal = Signal(
                side=raw.side,
                entry_price=raw.entry_price,
                stop_price=raw.stop_price,
                take_profit_price=raw.take_profit_price,
                quantity=result.quantity,
                timestamp=raw.timestamp,
                metadata=raw.metadata,
            )
            order_result = client.place_market_and_sl_tp(config.symbol, signal)
            if order_result.success:
                last_signal_ts = time.time()
                send_telegram(
                    f"Entry {raw.side.value} {config.symbol} qty={result.quantity} entry={order_result.avg_price or raw.entry_price:.3f} SL={raw.stop_price:.3f} TP={raw.take_profit_price:.3f}",
                    config.telegram_bot_token,
                    config.telegram_chat_id,
                )
            time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Shutdown by user")
            send_telegram("Trading bot stopped (user request).", config.telegram_bot_token, config.telegram_chat_id)
            break
        except Exception as e:
            logger.exception("Live loop error: %s", e)
            time.sleep(5)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Trading Bot CLI")
    parser.add_argument("mode", choices=["backtest", "live"], help="Run backtest or live")
    parser.add_argument("--config", type=Path, default=None, help="Path to config.yaml")
    args = parser.parse_args()
    if args.mode == "backtest":
        return run_backtest(args.config)
    return run_live(args.config)


if __name__ == "__main__":
    exit(main())
