# Deployment and Monitoring

This repository now has a local production-style Compose stack:

- `backend`: FastAPI operator API and metrics endpoint
- `frontend`: Nginx-served React dashboard
- `postgres`: persistent trading data
- `redis`: market-data pub/sub and cache
- `market-data`: optional Binance kline WebSocket worker
- `prometheus`: optional metrics scraper
- `grafana`: optional operational dashboard

## Local Compose

```powershell
docker compose up --build
docker compose --profile market-data up --build
docker compose --profile monitoring up --build
```

The backend exposes:

- `GET /health`: process liveness
- `GET /ready`: database readiness
- `GET /metrics`: Prometheus metrics

The default local monitoring profile is intentionally simple. Prometheus scrapes `backend:8000/metrics`, and Grafana loads the bundled `Trading Bot Overview` dashboard.

## Required Production Environment

Set these through VPS environment files, Docker secrets, Doppler, GitHub environment secrets, or the deployment platform secret manager. Do not commit real values.
Use `deploy/vps.env.example` as the checklist template.

```env
APP_ENV=production
API_TOKEN=replace-with-strong-operator-token
DATABASE_URL=postgresql+psycopg://...
REDIS_URL=redis://...
USE_TESTNET=true
CONFIRM_LIVE_TRADING=false
BINANCE_TESTNET_API_KEY=...
BINANCE_TESTNET_API_SECRET=...
BINANCE_MAINNET_API_KEY=...
BINANCE_MAINNET_API_SECRET=...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
METRICS_ENABLED=true
METRICS_TOKEN=replace-with-strong-metrics-token
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=replace-with-strong-password
```

Keep `USE_TESTNET=true` until testnet order placement, reconciliation, kill switch, and manual recovery have been exercised on the target VPS.

## Prometheus and Grafana

Prometheus configuration lives in `monitoring/prometheus/prometheus.yml`.
For production token-protected scraping, adapt `monitoring/prometheus/prometheus.auth-example.yml` and mount the token from a secret file.

Grafana provisioning lives in:

- `monitoring/grafana/provisioning/datasources/prometheus.yml`
- `monitoring/grafana/provisioning/dashboards/dashboards.yml`
- `monitoring/grafana/dashboards/trading-bot-overview.json`

Metrics currently include:

- API request count and latency
- database readiness
- running bot sessions
- open positions
- unprotected/manual-review orders
- risk-control flags
- risk event counts by severity
- persisted record counts for signals, orders, positions, trades, backtests, and AI reports

## Uptime Monitoring

External uptime monitors should probe:

- `/health` for basic process liveness
- `/ready` for database-backed service readiness

Use `/ready` for deployment health gates and `/health` for lightweight load balancer checks.

## Minimal VPS Runbook

1. Install Docker Engine and Docker Compose plugin.
2. Clone the repo on the VPS.
3. Create a private `.env` or platform secret set with production values.
4. Start with testnet only:

```bash
python main.py db-upgrade --revision head
docker compose --profile monitoring up -d --build
```

5. Confirm:

```bash
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/ready
curl -fsS -H "Authorization: Bearer $METRICS_TOKEN" http://127.0.0.1:8000/metrics
docker compose ps
docker compose logs --tail=100 backend
```

6. Configure DNS/TLS/reverse proxy outside this Compose file.
7. Only enable mainnet after a manual safety checklist and a small notional test.

## Incident Response

1. Hit `POST /risk/kill-switch` from the dashboard or API.
2. Check Binance directly for open positions and open reduce-only orders.
3. Review `risk_events`, `orders.requires_manual_review`, and Telegram emergency alerts.
4. Export logs and database rows before restarting services.
5. Restart only after confirming no position is unintentionally unprotected.

## Known Deployment Gaps

- Alembic migration commands are available, but automated zero-downtime migration orchestration is still deferred.
- Prometheus auth is endpoint-level; production deployments should keep Prometheus on a private network or add reverse-proxy authentication.
- Grafana uses local Compose defaults unless overridden by environment variables.
- Backups, TLS, DNS, and VPS firewall rules are documented here but not automated.
