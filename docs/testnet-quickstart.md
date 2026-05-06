# Testnet Quickstart

This guide starts the full local platform in testnet-safe mode.

## Prerequisites

- Python 3.11+
- Node 22+
- Docker Desktop
- Docker Compose plugin
- Binance USDT-M Futures testnet API key

## 1. Install Backend Dependencies

```powershell
py -m pip install -r requirements.txt
```

## 2. Configure `.env`

Copy `.env.example` to `.env` and fill:

```env
APP_ENV=local
USE_TESTNET=true
CONFIRM_LIVE_TRADING=false
BINANCE_TESTNET_API_KEY=...
BINANCE_TESTNET_API_SECRET=...
API_TOKEN=local-dev-token
METRICS_ENABLED=true
```

Do not put mainnet keys in `.env` while learning the platform.

## 3. Run Verification

```powershell
py -m pytest tests/ -q --basetemp C:\Users\Preethve\lwk-futures-Trading-Bot\pytest_tmp
py -m ruff check .
py -m mypy app --strict
npm test --prefix frontend
npm run build --prefix frontend
docker compose config
```

## 4. Start The Stack

```powershell
docker compose --profile monitoring up --build
```

Useful URLs:

- Dashboard: `http://localhost:8080`
- API docs: `http://localhost:8000/docs`
- Health: `http://localhost:8000/health`
- Readiness: `http://localhost:8000/ready`
- Metrics: `http://localhost:8000/metrics`
- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3000`

## 5. Start Market Data

Use the market-data profile when you want Redis-backed kline streaming:

```powershell
docker compose --profile market-data --profile monitoring up --build
```

Set:

```env
MARKET_DATA_SOURCE=redis
SYMBOLS=ZECUSDT,BTCUSDT,ETHUSDT
TIMEFRAME=5m
```

## 6. Backtest Before Live

```powershell
py main.py backtest
py main.py backtest-multi --report-json reports/backtests/multi.json
py main.py walk-forward --report-json reports/optimizations/walk_forward.json
```

## 7. Testnet Live Loop

Only after verification:

```powershell
py main.py live
```

Watch:

- dashboard live status
- risk controls
- order events
- Telegram alerts, if configured
- Binance testnet open positions

## 8. Stop Safely

Use the dashboard kill switch first if the bot is running:

```http
POST /risk/kill-switch
```

Then stop local services:

```powershell
docker compose down
```
