# Exchange Lifecycle Reconciliation

The exchange lifecycle reconciler is a one-shot operator sweep for keeping local order, fill, and position state aligned with Binance.

## Command

```powershell
py main.py reconcile-lifecycle --config config.yaml --limit 100
```

The command requires Binance API credentials. It uses the configured symbol list, or the single configured symbol when `SYMBOLS` is empty.

## What It Reconciles

- Polls Binance order status for persisted orders with an `exchange_order_id`.
- Persists `exchange_status`, `filled_quantity`, `remaining_quantity`, `avg_price`, and `last_reconciled_at`.
- Aggregates persisted `exchange_fills` by `exchange_order_id` so partial fills are reflected even when exchange order status lags.
- Syncs the local open position snapshot from Binance account position state.
- Emits `position_drift_detected` risk events when local and exchange positions disagree.
- Cancels stale reduce-only stop/take-profit orders when Binance reports no open position.

## Safety Boundaries

- The reconciler cancels stale reduce-only protection only when the exchange position is flat.
- It does not create replacement stop-loss or take-profit orders from stale local data.
- It marks rejected, expired, or unfilled cancelled entry orders as manual-review failures.
- It records risk events for terminal order statuses, missing order statuses, position drift, and stale protection cancellations.

## Follow-Up Hardening

- Run this command on a schedule from the deployment host or automation runner.
- Add account balance reconciliation after wallet-equity persistence exists.
- Add exchange order event WebSocket ingestion for lower-latency status updates.
