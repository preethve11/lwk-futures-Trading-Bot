# Changelog

All notable changes are tracked here.

## Unreleased

- Add `adaptive_momentum_breakout` research strategy with Donchian breakout, EMA(50/200), ADX, volume, spread, funding, funding-delta, open-interest, ADL, liquidation, timing, and expected-cost gates.
- Add crowding, correlation, and drawdown-pause risk helpers plus adaptive strategy tests.
- Add adaptive strategy research/paper-validation CLI wrappers and strategy-research output for crowding, day/hour timing, expected cost/edge, and symbol concentration diagnostics.
- Add Binance Futures funding, open-interest, ADL quantile, and force-order diagnostic methods, plus market-data download flags for funding/OI visibility.
- Add walk-forward embargo sizing and stricter default live-promotion gates for research candidates.
- Add config-driven `session_breakout` strategy with NSE/London/New York session opens, 2-hour pre-session range, 5m-disabled default, minimum range-width gate, EMA(50) regime filter, ADX chop filter, rejected-signal diagnostics, and SL/TP research columns.
- Add rejected-signal JSON artifacts, intended-vs-actual exit diagnostics, regime/session/filter breakdowns in strategy research, and strategy comparison reporting.
- Add `strategy-research` diagnostics for trade distribution, timeframe cost drag, outlier concentration, and direct losing-strategy root-cause analysis.
- Add strategy performance gate for live promotion, mainnet enforcement, API/dashboard visibility, CLI smoke, and tests.
- Fix backtest trade logs to record actual entry timestamps instead of `datetime.min`.
- Add read-only mainnet readiness checklist CLI, small-notional protocol docs, WebSocket fanout tests, and frontend component/WebSocket rendering tests.
- Add guarded Binance Futures testnet execution validation for `session_breakout_ZECUSDT_15m` with SL/TP verification, fill cost measurement, cleanup, reports, and tests.
- Add quant research foundation with market-data/features/regimes/strategy/backtest/execution/allocation/health/log tables, repositories, migration, lookahead-safe features, professional regime detector, CCXT OHLCV ingestion, Streamlit dashboard entrypoint, smart routing, allocator, and health tracker.
- Add account/equity reconciliation with Binance wallet polling, live equity snapshot persistence, drift alerts, API/dashboard visibility, metrics, and migration.
- Add exchange lifecycle reconciliation command with order status polling, partial-fill aggregation, position drift detection, stale reduce-only cancellation, and order lifecycle migration.
- Add one-shot `recover-unprotected` command for persisted `FAILED_UNPROTECTED` orders with protection recheck, emergency close, alerts, and audit events.
- Add exchange-fill reconciliation ledger, idempotent closed-PnL trade creation, API visibility, metrics, and migration.
- Add Alembic migration foundation and database migration CLI commands.
- Add GitHub/portfolio documentation polish.
- Add current README architecture diagram, safety position, quickstart, and roadmap status.
- Add contribution and security policies.

## 2026-05-06

- Added deployment monitoring stack with `/ready`, `/metrics`, Prometheus, Grafana, VPS env template, and incident runbook.
- Added advisory-only AI trade journal with nonblocking queue, OpenAI Responses client, persistence, API route, dashboard display, docs, and tests.
- Added Monte Carlo simulation with report export.
- Added walk-forward optimizer with Optuna and JSON reports.
- Added Binance WebSocket market-data service with Redis pub/sub/cache.
- Added multi-symbol backtest runner and Docker Compose stack for backend, frontend, Postgres, and Redis.
- Added FastAPI operator API, token auth, WebSocket live events, repository-backed routes, and dashboard shell.
- Added execution safety reconciliation worker, protected order result, alert severity levels, and async alert queue.
- Added SQLAlchemy persistence, repositories, DB helpers, order state machine, and live/backtest persistence hooks.
- Added settings refactor, structured JSON logging, strategy registry, live trader worker, and Binance symbol-info caching.
- Added CI, strategy/backtest tests, live trading guard, backtest date filtering, and historical data loaders.

