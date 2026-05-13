# LWK Futures Trading Bot

[![CI](https://github.com/preethve11/lwk-futures-Trading-Bot/actions/workflows/ci.yml/badge.svg)](https://github.com/preethve11/lwk-futures-Trading-Bot/actions/workflows/ci.yml)

Production-oriented automated crypto futures trading platform for Binance USDT-M Futures. The project includes a strategy engine, risk controls, exchange execution safety, persistence, FastAPI operator API, React dashboard, backtesting, optimization, simulation, market-data streaming, monitoring, and deployment assets.

This repository is built for research, testnet operation, and engineering portfolio review. Treat real-money trading as an additional production-hardening phase, not a default mode.

## What Is Included

- EMA/RSI/VWAP/volume scalping strategy with ATR stops and take-profits.
- Session-open breakout strategy for NSE, London, and New York opens with 2-hour pre-session range, EMA(50), ADX, range-width gates, and rejected-signal diagnostics.
- Adaptive momentum breakout research strategy with Donchian breakout, EMA(50/200), ADX, volume, funding, open-interest, ADL, liquidation, spread, timing, and expected-cost gates.
- Strict risk controls: fixed dollar risk, daily loss lock, drawdown lock, risk-reward checks, min notional, manual pause, and kill switch.
- Binance Futures execution client with symbol-info caching and live trading guard.
- Order protection state machine and reconciliation worker for SL/TP verification and emergency close.
- Live account/equity reconciliation with wallet snapshots, drift alerts, dashboard visibility, and Prometheus gauges.
- SQLAlchemy persistence for sessions, signals, orders, positions, trades, risk events, backtests, and AI reports.
- Repository layer for database access.
- FastAPI operator API with token auth, WebSocket live events, readiness, and Prometheus metrics.
- React/Vite dashboard for live status, risk controls, trades, backtests, equity curve, logs/events, and AI journal output.
- Multi-symbol backtesting, JSON report export, walk-forward optimization, Monte Carlo simulation, and strategy research diagnostics.
- Quant research storage for OHLCV candles, feature snapshots, market regimes, strategy candidates, validation results, execution quality, allocator decisions, health checks, and system logs.
- Lookahead-safe feature library with returns, volatility, ATR, RSI, EMA/SMA, MACD, Bollinger Bands, VWAP, volume ratio, momentum, z-score, ADX, trend strength, volatility percentile, and spread proxy.
- Professional regime detector for trend, volatility, liquidity, and combined regime IDs.
- CCXT-based Binance OHLCV downloader for research data ingestion.
- Binance WebSocket kline market-data service with Redis pub/sub/cache.
- Advisory-only AI trade journal. AI can explain decisions but cannot place orders or mutate trading state.
- Docker Compose stack for backend, frontend, Postgres, Redis, optional market-data worker, Prometheus, and Grafana.
- CI pipeline with lint, strict app mypy, tests, frontend build, Docker builds, Compose config, and gitleaks secret scanning.

## Architecture

```mermaid
flowchart LR
    subgraph Inputs
        YAML["config.yaml"]
        ENV[".env / secrets"]
        BINANCE_WS["Binance kline WebSocket"]
        CSV["CSV / historical data"]
    end

    subgraph Core
        SETTINGS["Pydantic Settings"]
        REGISTRY["StrategyRegistry"]
        STRATEGY["EMA RSI VWAP Strategy"]
        RISK["RiskManager"]
        EXEC["Execution Client"]
        RECON["ReconciliationWorker"]
        ACCOUNT["Account Equity Reconciler"]
    end

    subgraph Persistence
        DB[("Postgres / SQLite")]
        REPOS["Repository Layer"]
    end

    subgraph Operators
        API["FastAPI API"]
        WS["/ws/live"]
        DASH["React Dashboard"]
        ALERTS["Async Alerts"]
        METRICS["/metrics"]
    end

    subgraph Research
        BACKTEST["Backtest Engine"]
        MULTI["Multi-symbol Runner"]
        WFO["Walk-forward Optimizer"]
        MC["Monte Carlo"]
        AI["AI Trade Journal"]
    end

    BINANCE_WS --> REDIS[("Redis")]
    REDIS --> STRATEGY
    CSV --> BACKTEST
    YAML --> SETTINGS
    ENV --> SETTINGS
    SETTINGS --> REGISTRY
    REGISTRY --> STRATEGY
    STRATEGY --> RISK
    RISK --> EXEC
    EXEC --> RECON
    EXEC --> ACCOUNT
    RECON --> REPOS
    ACCOUNT --> REPOS
    RISK --> REPOS
    BACKTEST --> REPOS
    MULTI --> REPOS
    WFO --> BACKTEST
    MC --> REPOS
    AI --> REPOS
    REPOS --> DB
    API --> REPOS
    DASH --> API
    API --> WS
    API --> METRICS
    EXEC --> ALERTS
```

More detail: [docs/architecture.md](docs/architecture.md)

## 5-Minute Testnet Quickstart

1. Install Python 3.11+, Node 22+, Docker Desktop, and Docker Compose.
2. Clone the repo and install backend dependencies:

```powershell
py -m pip install -r requirements.txt
```

3. Copy `.env.example` to `.env`, then fill only testnet-safe values:

```env
USE_TESTNET=true
CONFIRM_LIVE_TRADING=false
BINANCE_TESTNET_API_KEY=...
BINANCE_TESTNET_API_SECRET=...
API_TOKEN=local-dev-token
```

4. Run local verification:

```powershell
py -m pytest tests/ -q --basetemp C:\Users\Preethve\lwk-futures-Trading-Bot\pytest_tmp
py -m ruff check .
py -m mypy app --strict
```

5. Start the platform:

```powershell
docker compose --profile monitoring up --build
```

6. Open:

- Dashboard: `http://localhost:8080`
- API docs: `http://localhost:8000/docs`
- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3000`

Full guide: [docs/testnet-quickstart.md](docs/testnet-quickstart.md)

## Common Commands

```powershell
# Backtest
py main.py backtest

# Session-open breakout research run. 5m is disabled by default; use 15m or 1h.
py main.py backtest --strategy session_breakout --symbol ZECUSDT --timeframe 1h --add-regime-labels --show-rejected

# Inspect rejection reasons from the latest backtest
py main.py rejected-signals reports/latest/rejected_signals.json

# Multi-symbol backtest, using SYMBOLS from env or config.yaml
py main.py backtest-multi --report-json reports/backtests/multi.json

# Walk-forward optimization
py main.py walk-forward --report-json reports/optimizations/walk_forward.json

# Monte Carlo simulation
py main.py monte-carlo --returns-json reports/backtests/example.json --report-json reports/monte_carlo/example.json

# Explain strategy losses from a generated trade log
py main.py strategy-research --trades-csv reports/paper_validation/run_id/trade_log.csv

# Include regime/session/filter diagnostics from the latest backtest artifacts
py main.py strategy-research reports/latest/trade_log.csv --group-by-regime

# Run the adaptive momentum breakout research candidate across configured local datasets
py main.py strategy-research-runner --strategy adaptive_momentum_breakout --symbols BTCUSDT ETHUSDT SOLUSDT BNBUSDT LINKUSDT --timeframes 1h 15m --group-by-regime

# Paper-validation report for the adaptive candidate
py main.py paper-validation --strategy adaptive_momentum_breakout --symbols BTCUSDT ETHUSDT SOLUSDT BNBUSDT LINKUSDT --timeframes 1h 15m --group-by-regime

# Compare baseline and filtered variants side by side
py main.py strategy-compare --baseline ema_rsi_vwap --variants ema_rsi_vwap_trend_only ema_rsi_vwap_high_vol ema_rsi_vwap_combined --symbols ZECUSDT BTCUSDT ETHUSDT --timeframes 1h 15m

# API
py main.py api --host 127.0.0.1 --port 8000

# Market-data WebSocket worker
py main.py market-data

# Download and persist CCXT Binance OHLCV research data, optionally printing funding/OI diagnostics
py main.py download-market-data --symbols BTCUSDT ETHUSDT SOLUSDT BNBUSDT LINKUSDT --timeframes 15m 1h --limit 500 --include-funding --include-open-interest

# Streamlit quant dashboard
streamlit run trading_bot/dashboard/streamlit_app.py

# Database migrations
py main.py db-upgrade --revision head
py main.py db-current

# Mainnet readiness, read-only
py main.py mainnet-checklist --small-notional-usd 10

# Binance Futures testnet execution validation for the current candidate only
py main.py testnet-execution-check --symbol BTCUSDT --timeframe 1h --small-notional-usd 10 --max-fee-bps 6 --max-slippage-bps 10

# Strategy live-promotion gate
py main.py strategy-gate

# Account/equity reconciliation
py main.py reconcile-account --asset USDT

# Exchange lifecycle reconciliation
py main.py reconcile-lifecycle --limit 100

# Live loop, testnet first
py main.py live
```

## API Surface

Key endpoints:

- `GET /health`
- `GET /ready`
- `GET /metrics`
- `GET /configs`, `POST /configs`
- `GET /backtests`, `POST /backtests/run`, `POST /backtests/run-multi`
- `GET /trades`, `GET /trades/{id}`
- `GET /sessions`, `POST /sessions/start`, `POST /sessions/stop`
- `GET /risk/state`, `POST /risk/state`, `POST /risk/kill-switch`, `GET /risk/events`
- `GET /risk/performance-gate`
- `GET /signals`
- `GET /positions`
- `GET /account/snapshots`
- `GET /ai-reports`
- `WebSocket /ws/live`

Protected operator routes use `X-API-Token` or `Authorization: Bearer <token>` when `API_TOKEN` is configured.

## Safety Position

This project is deliberately conservative:

- Mainnet requires `USE_TESTNET=false` and `CONFIRM_LIVE_TRADING=true`.
- The live loop must not block on Telegram, AI, or dashboard calls.
- SL/TP protection is verified after entry.
- Failed protection can trigger emergency close and manual review.
- Live account equity is persisted from Binance wallet state and drift emits operator alerts.
- Mainnet live trading can be blocked by the strategy performance gate when recent backtest metrics are weak or stale.
- AI reports are advisory-only and cannot call execution clients or mutate state.
- Metrics and logs are operational aids, not trading signals.

Read before live use: [docs/safety.md](docs/safety.md)

## Backtesting And Research

Reports include Sharpe, Sortino, max drawdown, win rate, profit factor, average R:R, equity curves, and JSON export paths. Use walk-forward and Monte Carlo before trusting a parameter set.

`strategy-research` consumes a paper-validation `trade_log.csv` and explains losses by symbol, timeframe, market condition, hour-of-day, exit reason, transaction-cost drag, and outlier concentration. It is designed to answer whether a bad run is driven by 5m noise, costs, broad negative expectancy, or a small number of large losses.

For the session-open breakout workflow, keep 5m disabled until it proves positive out-of-sample expectancy. Start with 15m and 1h, inspect `reports/latest/rejected_signals.json`, then use `strategy-research --group-by-regime` to review performance by session, range-width bucket, EMA alignment, and ADX bucket.

For the adaptive momentum breakout workflow, keep real live trading disabled and use 15m/1h only. The candidate must survive funding-rate level and delta checks, open-interest spike checks, ADL/liquidation stress checks, spread/cost gates, correlation exposure caps, walk-forward embargo validation, Monte Carlo stress, and Binance testnet execution measurement before live discussion.

Current live-promotion defaults are intentionally stricter for research candidates: at least 100 trades, profit factor >= 1.25, positive expectancy, and max drawdown <= 15%.

Example report: [docs/example-backtest-report.md](docs/example-backtest-report.md)
Strategy research guide: [docs/strategy-research.md](docs/strategy-research.md)
Session breakout diagnostics: [docs/session-breakout-diagnostics.md](docs/session-breakout-diagnostics.md)
Strategy comparison workflow: [docs/strategy-comparison.md](docs/strategy-comparison.md)

## Deployment

Local production-style stack:

```powershell
docker compose up --build
docker compose --profile market-data up --build
docker compose --profile monitoring up --build
```

Deployment and incident runbook: [docs/deployment-monitoring.md](docs/deployment-monitoring.md)

Database migrations: [docs/database-migrations.md](docs/database-migrations.md)

Mainnet readiness: [docs/mainnet-dry-run-checklist.md](docs/mainnet-dry-run-checklist.md)

Small-notional test protocol: [docs/small-notional-test-protocol.md](docs/small-notional-test-protocol.md)

Testnet execution validation: [docs/testnet-execution-validation.md](docs/testnet-execution-validation.md)

Quant research platform: [docs/quant-research-platform.md](docs/quant-research-platform.md)

Strategy gate: [docs/strategy-performance-gate.md](docs/strategy-performance-gate.md)

## Repository Map

```text
app/
  ai/              advisory-only AI journal
  analytics/       Monte Carlo simulation and strategy research diagnostics
  api/             FastAPI app, routers, schemas, event bus
  backtesting/     multi-symbol and walk-forward tooling
  core/            Pydantic settings
  market_data/     Binance WebSocket + Redis market data
  monitoring/      readiness and Prometheus metrics
  persistence/     SQLAlchemy models, repositories, state machine
  strategies/      strategy registry
  workers/         live trader and reconciliation worker
frontend/          React/Vite operator dashboard
monitoring/        Prometheus and Grafana provisioning
deploy/            deployment env templates
docs/              operator and roadmap documentation
tests/             backend tests
trading_bot/       core strategy, risk, execution, analytics primitives
```

## Verification

Current CI runs:

- `ruff check .`
- `mypy app --strict --ignore-missing-imports`
- `pytest tests/`
- market-data CLI smoke
- Monte Carlo CLI smoke
- frontend install/test/build
- backend Docker build
- frontend Docker build
- base Compose config
- monitoring Compose config
- gitleaks secret scan

Local full check:

```powershell
py -m pytest tests/ -q --basetemp C:\Users\Preethve\lwk-futures-Trading-Bot\pytest_tmp
py -m ruff check .
py -m mypy app --strict
npm test --prefix frontend
npm run build --prefix frontend
docker compose config
docker compose --profile monitoring config
```

## Roadmap Status

Completed:

- Day 1: CI, tests, Pydantic settings foundation, live trading guard, backtest date filtering, historical data loading.
- Day 2: runtime refactor, settings wrapper, structured logging, strategy registry, live worker, Binance symbol cache.
- Day 3: persistence models, repositories, DB helpers, order state machine, live/backtest persistence hooks.
- Day 4: reconciliation worker, protected order result, alert severity, async alert queue, emergency path tests.
- Day 5: FastAPI API, token auth, repository-backed routes, WebSocket live events.
- Day 6: React dashboard shell and core operator pages.
- Day 7: multi-symbol backtesting, JSON reports, Docker Compose with Postgres/Redis/frontend/backend.
- Week 2: market-data WebSocket/Redis service, walk-forward optimizer, Monte Carlo simulation, AI trade journal, deployment monitoring.
- Production hardening: exchange lifecycle reconciliation, failed-unprotected recovery, exchange-fill ledger, Alembic migrations, and account/equity reconciliation.
- Quant research foundation: PostgreSQL-ready research tables, CCXT market-data ingestion, feature library, professional regime detector, smart routing policy, meta-allocator, performance health tracker, and Streamlit dashboard entrypoint.

Still recommended:

- Paper/testnet campaign with real Binance testnet credentials for `session_breakout_ZECUSDT_15m`.
- VPS TLS/reverse-proxy automation.
- Backup and restore automation.
- Browser-level dashboard regression tests.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Security

Do not commit secrets. Report security issues using [SECURITY.md](SECURITY.md).

## License

MIT License. See [LICENSE](LICENSE).
