# Changelog

All notable changes are tracked here.

## Unreleased

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

