# Mainnet Dry-Run Checklist

This checklist is read-only until the final supervised small-notional window. Do not run `py main.py live` against mainnet until every automated check is understood and the manual checks are complete.

## Automated Local Check

```powershell
py main.py mainnet-checklist --small-notional-usd 10
```

The command does not call Binance and does not place orders. It validates local configuration for:

- mainnet mode selection
- explicit live confirmation
- mainnet API credentials presence
- API token presence
- Postgres/database migration discipline
- small-notional risk budget
- daily loss cap
- drawdown lock
- Telegram alert readiness
- account/equity reconciliation thresholds
- strategy performance gate enforcement
- market-data source

Use `--allow-failures` only for rehearsal output in local/testnet environments.

## Manual Preflight

1. Confirm CI is green on the exact commit being deployed.
2. Run `py main.py db-upgrade --revision head` against the target database.
3. Start API/dashboard with `API_TOKEN` configured.
4. Confirm `/ready` returns `ok`.
5. Confirm `/metrics` is private or protected.
6. Confirm dashboard kill switch toggles and updates persisted risk state.
7. Confirm Telegram receives an INFO test alert from a non-order path.
8. Run `py main.py reconcile-account --asset USDT` and compare wallet/equity with Binance.
9. Run `py main.py reconcile-lifecycle --limit 100` and confirm no unexpected open position/order drift.
10. Run `py main.py strategy-gate` and confirm the latest validation run passes.
11. Confirm Binance account mode, leverage, margin mode, and symbol filters manually in Binance.
12. Confirm no open positions and no stale reduce-only orders on Binance.
13. Confirm API keys are restricted to required futures permissions and have withdrawal disabled.

## Mainnet Configuration Window

Only during the supervised mainnet test window:

```env
USE_TESTNET=false
CONFIRM_LIVE_TRADING=true
RISK_PER_TRADE_USD=1
MAX_DAILY_LOSS_USD=3
MAX_DRAWDOWN_PCT=10
ACCOUNT_EQUITY_DRIFT_THRESHOLD_USD=1
DATABASE_AUTO_CREATE_TABLES=false
LIVE_STRATEGY_GATE_REQUIRED_FOR_MAINNET=true
```

Keep a Binance browser session open and ready to manually close positions.

## Abort Conditions

Stop immediately and enable the kill switch if:

- account equity differs from Binance by more than the configured drift threshold
- lifecycle reconciliation reports position drift
- any order enters `FAILED_UNPROTECTED`
- Telegram/alerts are unavailable
- dashboard/API is unreachable
- Binance shows an unexpected position or open order
- latency, rate-limit errors, or partial fills are not understood
