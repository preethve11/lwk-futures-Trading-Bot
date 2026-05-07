# Small-Notional Mainnet Test Protocol

This protocol is for a single supervised real-money validation after testnet and dry-run checks pass. It is intentionally small, reversible, and operator-driven.

## Scope

- One symbol only.
- One live session only.
- One entry attempt only.
- Small risk budget, normally 1 to 10 USD maximum risk.
- No optimization, AI automation, or unattended execution during the test.

## Sequence

1. Merge only green CI code to `main`.
2. Deploy backend, frontend, Postgres, Redis, and monitoring from the verified commit.
3. Run database migrations.
4. Start API/dashboard, not the live trader.
5. Enable the dashboard kill switch before any live process starts.
6. Run account reconciliation and confirm wallet/equity matches Binance.
7. Run exchange lifecycle reconciliation and confirm no drift.
8. Disable the kill switch only when Binance, dashboard, alerts, and logs are all visible.
9. Start `py main.py live` with:
   - `USE_TESTNET=false`
   - `CONFIRM_LIVE_TRADING=true`
   - `RISK_PER_TRADE_USD` at the chosen small risk
   - `MAX_DAILY_LOSS_USD` no more than 3x that small risk
10. Watch Binance and dashboard until either one protected trade is accepted or the session times out.
11. After the first entry, confirm stop-loss and take-profit orders exist on Binance.
12. Run `py main.py reconcile-lifecycle --limit 100`.
13. If the trade closes, run exchange fill reconciliation via the live loop or recent-fill path and confirm closed PnL appears in API/dashboard.
14. Stop the live process.
15. Enable the kill switch.
16. Run account reconciliation again and compare wallet/equity with Binance.
17. Export logs, risk events, orders, fills, trades, and account snapshots for review.

## Required Pass Criteria

- Live guard blocks mainnet unless `CONFIRM_LIVE_TRADING=true`.
- Dashboard kill switch blocks new trading.
- Entry order is persisted.
- SL/TP protection is persisted and visible on Binance.
- Reconciliation reports no unresolved drift.
- Account snapshots bracket the test before and after.
- Any realized PnL is created idempotently from exchange fills.
- Operator can stop the process without leaving stale local state.

## Required Abort Actions

1. Enable kill switch.
2. Stop the live process.
3. Inspect Binance for open positions and orders.
4. Manually close or protect any open exposure.
5. Run account, fill, lifecycle, and failed-unprotected reconciliation.
6. Do not restart until the incident is documented.
