# Architecture

This project is split into operational layers so strategy logic, risk controls, execution, persistence, and operator tooling can evolve independently.

## Runtime Flow

```mermaid
sequenceDiagram
    participant Worker as LiveTrader
    participant Market as Market Data
    participant Strategy as Strategy
    participant Risk as RiskManager
    participant Exchange as Binance Client
    participant Recon as ReconciliationWorker
    participant DB as Repositories
    participant Alerts as Alert Queue

    Worker->>Market: load closed candles
    Market-->>Worker: OHLCV dataframe
    Worker->>Strategy: compute indicators and signal
    Strategy-->>Worker: signal or no signal
    Worker->>Risk: validate signal and size quantity
    Risk-->>Worker: allowed/rejected decision
    Worker->>DB: persist signal/risk event
    alt allowed
        Worker->>Exchange: place market entry and protection orders
        Exchange-->>Worker: order IDs
        Worker->>Recon: verify SL/TP protection
        Recon->>Exchange: fetch order status with retry/backoff
        Recon-->>Worker: protected result or emergency action
        Worker->>DB: persist order, protection state, risk events
        Worker->>Alerts: enqueue operator alert
    else rejected
        Worker->>DB: persist rejection
        Worker->>Alerts: enqueue warning
    end
```

## Main Packages

- `app/core`: typed settings and config loading.
- `app/strategies`: strategy registry and app-facing strategy creation.
- `trading_bot/strategies`: strategy primitives and EMA/RSI/VWAP implementation.
- `trading_bot/risk`: position sizing and risk validation.
- `trading_bot/execution`: exchange abstraction and Binance Futures adapter.
- `app/workers`: live trading loop and reconciliation worker.
- `app/persistence`: SQLAlchemy models, repositories, DB helpers, and order state machine.
- `app/api`: FastAPI app, routers, schemas, event bus, and route services.
- `frontend`: React/Vite operator dashboard.
- `app/market_data`: Binance WebSocket kline service and Redis integration.
- `app/backtesting`: multi-symbol and walk-forward tooling.
- `app/analytics`: Monte Carlo simulation.
- `app/ai`: advisory-only trade journal service.
- `app/monitoring`: readiness probes and Prometheus metrics.

## Persistence Model

```mermaid
erDiagram
    BOT_SESSIONS ||--o{ SIGNALS : records
    BOT_SESSIONS ||--o{ ORDERS : owns
    BOT_SESSIONS ||--o{ POSITIONS : snapshots
    BOT_SESSIONS ||--o{ TRADES : closes
    BOT_SESSIONS ||--o{ RISK_EVENTS : emits
    BOT_SESSIONS ||--o{ AI_REPORTS : explains
    SIGNALS ||--o{ ORDERS : triggers
    SIGNALS ||--o{ TRADES : links
    SIGNALS ||--o{ AI_REPORTS : explains
    ORDERS ||--o{ TRADES : fills
    TRADES ||--o{ AI_REPORTS : reviews
```

Models currently include:

- `BotSessionModel`
- `ConfigModel`
- `RiskStateModel`
- `SignalModel`
- `OrderModel`
- `PositionModel`
- `TradeModel`
- `RiskEventModel`
- `BacktestRunModel`
- `AIReportModel`

## Execution Safety

Order protection state is tracked through:

- `PENDING`
- `ENTRY_PLACED`
- `TP_PLACED`
- `SL_PLACED`
- `PROTECTED`
- `FAILED_UNPROTECTED`

After a market entry, reconciliation verifies stop-loss and take-profit protection on Binance. Missing protection is retried with backoff. If protection is still absent, the worker can trigger emergency close, persist manual-review state, and emit critical alerts.

## API And Dashboard

The dashboard talks to FastAPI through a small API client layer. The API uses repository classes rather than scattered direct SQLAlchemy queries. Live updates are pushed through `/ws/live`.

Operator routes are token-protected when `API_TOKEN` is configured. In production, an empty API token is rejected.

## Market Data

The market-data worker subscribes to Binance kline streams and publishes closed-candle updates to Redis. The live strategy loop can run from Redis market data or REST polling, controlled by `MARKET_DATA_SOURCE`.

## Research Tooling

Backtesting and research features share the same strategy and risk primitives where practical:

- Single-symbol backtest
- Multi-symbol aggregate backtest
- Walk-forward optimization with Optuna
- Monte Carlo simulation from trade returns
- JSON report export

## Monitoring

FastAPI exposes:

- `/health`: process liveness
- `/ready`: readiness and optional DB check
- `/metrics`: Prometheus scrape endpoint

Compose can run Prometheus and Grafana with:

```powershell
docker compose --profile monitoring up --build
```

## Deferred Production Hardening

- Alembic migration runner.
- Exchange-led fill reconciliation from Binance user-data streams.
- Full backup and restore automation.
- TLS/reverse proxy automation.
- More extensive dashboard and WebSocket tests.

