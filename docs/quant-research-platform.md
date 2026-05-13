# Quant Research Platform

This project is a research, validation, paper/testnet execution, and monitoring system. It is not a guaranteed-profit bot.

## New Research Storage

The Alembic revision `20260513_0005` adds these PostgreSQL-ready tables:

- `market_data`
- `features`
- `regimes`
- `strategies`
- `backtest_results`
- `executions`
- `portfolio_allocations`
- `performance_health`
- `system_logs`

Existing runtime tables remain in place for sessions, signals, orders, positions, trades, exchange fills, account snapshots, risk events, AI reports, configs, and backtest runs.

## Market Data

Install dependencies, then run:

```powershell
py main.py db-upgrade --revision head
py main.py download-market-data --symbols BTCUSDT ETHUSDT SOLUSDT --timeframes 5m 15m 1h --limit 500
```

The downloader uses CCXT Binance USDT-M Futures, cleans OHLCV data, removes duplicate candles, counts missing candle slots, and persists rows into `market_data`.

## Feature Library

Feature generation lives in:

```text
trading_bot/features/feature_library.py
```

It includes returns, log returns, rolling volatility, ATR, RSI, EMA, SMA, MACD, Bollinger Bands, VWAP, volume ratio, momentum, price z-score, high-low range, ADX, trend strength, volatility percentiles, and a spread proxy.

By default, derived features are shifted one candle to reduce lookahead risk.

## Regime Detection

Regime detection lives in:

```text
trading_bot/regime/regime_detector.py
```

It labels:

- Trend: `STRONG_TREND`, `WEAK_TREND`, `RANGING`
- Volatility: `HIGH_VOL`, `MEDIUM_VOL`, `LOW_VOL`
- Liquidity: `HIGH_LIQ`, `LOW_LIQ`

The combined `regime_id` looks like:

```text
STRONG_TREND_HIGH_VOL_HIGH_LIQ
```

## Execution And Allocation

Added components:

- `trading_bot/execution/smart_order_router.py`: chooses `LIMIT`, `MARKET`, or `NONE` from urgency, spread proxy, and expected edge.
- `trading_bot/portfolio/meta_allocator.py`: equal-weight allocator with a hard 30% max strategy weight and health-based deallocation.
- `trading_bot/monitoring/performance_tracker.py`: classifies strategy health as `HEALTHY`, `WARNING`, `CRITICAL`, or `KILLED`.

Live mainnet execution remains disabled by default. Mainnet now requires both:

```env
ENABLE_LIVE_TRADING=true
CONFIRM_LIVE_TRADING=true
```

## Streamlit Dashboard

Run:

```powershell
streamlit run trading_bot/dashboard/streamlit_app.py
```

The dashboard reads the configured database and shows account equity, strategy health, current regimes, validation results, trades, portfolio allocations, market data, and risk events.

## Manual Setup Still Required

- Binance Testnet API key and secret for real testnet execution checks.
- PostgreSQL URL for durable research storage outside local SQLite.
- Telegram bot token and chat ID before relying on external alerts.
- TradingView webhook or alert setup if you want bot-vs-TradingView signal comparison.

## Next Build Step

The next high-value phase is a strategy research runner that generates 50-200 candidates, persists each candidate in `strategies`, persists validation metrics in `backtest_results`, and promotes only candidates that pass out-of-sample, regime, fee, slippage, and drawdown filters.
