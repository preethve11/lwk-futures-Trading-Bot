# Security Policy

## Supported Branch

Security fixes should target `main`.

## Reporting A Vulnerability

Do not open a public issue for secrets, authentication bypasses, exchange-order bugs, or vulnerabilities that could expose account data.

Use a private channel with the repository owner. Include:

- affected commit or branch
- reproduction steps
- expected impact
- logs or screenshots with secrets removed
- whether real funds or exchange credentials may be affected

## Secret Handling

- Never commit `.env`.
- Never put Binance, Telegram, OpenAI, database, Grafana, or metrics tokens in code.
- Use environment variables, Docker secrets, Doppler, GitHub environment secrets, or platform secret managers.
- Run gitleaks before pushing sensitive changes when possible.

## Production Exposure

Before exposing the platform:

- Set `APP_ENV=production`.
- Set a strong `API_TOKEN`.
- Set a strong `METRICS_TOKEN` or keep Prometheus private.
- Put the dashboard and API behind TLS.
- Restrict firewall ingress.
- Use testnet until the target environment has passed operational checks.

## AI Safety Boundary

The AI trade journal is advisory-only. Treat any path that lets AI place orders, change risk state, alter configs, or call execution clients as a security vulnerability.

