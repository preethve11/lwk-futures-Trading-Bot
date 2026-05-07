# Account Equity Reconciliation

Account equity reconciliation records the live Binance USDT-M wallet state as an auditable equity curve and alerts operators when the exchange balance drifts beyond configured thresholds.

## Command

```powershell
py main.py reconcile-account --config config.yaml --asset USDT
```

The command requires active Binance API credentials. It reads the futures account wallet state, persists an `account_snapshots` row, compares the latest equity and wallet balances with the prior snapshot, and emits a risk event plus alert when drift exceeds the configured thresholds.

## Live Loop Integration

The live worker runs this reconciliation periodically with:

```yaml
monitoring:
  account_reconciliation_interval_seconds: 300
  account_equity_drift_threshold_usd: 25.0
  account_equity_drift_threshold_pct: 5.0
```

Alerts use the existing nonblocking `AlertQueue`, so Telegram/network latency does not block order execution. Database writes are best-effort and isolated from order placement exceptions.

## Persisted Fields

`account_snapshots` stores:

- `asset`
- `wallet_balance`
- `unrealized_pnl`
- `margin_balance`
- `available_balance`
- `max_withdraw_amount`
- `event_time`
- raw exchange response for audit/debugging

The dashboard uses `margin_balance` as live account equity.

## API And Metrics

- `GET /account/snapshots?asset=USDT&limit=100`
- Prometheus gauges:
  - `trading_bot_account_equity{asset="USDT"}`
  - `trading_bot_account_wallet_balance{asset="USDT"}`
  - `trading_bot_account_available_balance{asset="USDT"}`
- Record count:
  - `trading_bot_persisted_records_total{table="account_snapshots"}`

## Safety Notes

- Balance drift is an operator alert, not an automated trading signal.
- Drift alerts do not directly pause or close positions.
- Operators should compare drift alerts with Binance deposits, withdrawals, funding, realized PnL, fees, and manual trades.
- Use the kill switch and exchange lifecycle reconciler when drift is unexplained.
