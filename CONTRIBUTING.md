# Contributing

This project is safety-sensitive because it can connect to a live futures exchange. Keep changes small, tested, and explicit.

## Development Setup

```powershell
py -m pip install -r requirements.txt
npm ci --prefix frontend
```

## Required Checks

Run before opening a PR:

```powershell
py -m pytest tests/ -q --basetemp C:\Users\Preethve\lwk-futures-Trading-Bot\pytest_tmp
py -m ruff check .
py -m mypy app --strict
py main.py db-current
npm test --prefix frontend
npm run build --prefix frontend
docker compose config
docker compose --profile monitoring config
```

## Coding Standards

- Keep strategy, risk, execution, persistence, API, and UI concerns separated.
- Use repository classes for database access from services/routes.
- Do not hardcode secrets or account identifiers.
- Use structured logging for runtime events.
- Keep live trading paths nonblocking for alerts, AI, dashboard calls, and other network side effects.
- Add tests for safety-critical behavior.
- Keep AI advisory-only. AI must not place orders or mutate state.

## Pull Request Checklist

- Describe the behavior change and safety impact.
- List verification commands and results.
- Include migration scripts for DB schema changes.
- Update docs when changing operator workflows.
- Avoid unrelated formatting churn.

## Branch Names

Use a descriptive branch name, for example:

```text
codex/exchange-reconciliation
codex/dashboard-websocket-tests
codex/alembic-migrations
```

