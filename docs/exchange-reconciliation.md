# Exchange Fill Reconciliation

This platform keeps a local exchange-fill ledger so Binance account-trade data can be reconciled against local analytics without duplicating records.

## What Is Persisted

- Raw Binance account trades are normalized into `exchange_fills`.
- `exchange_trade_id` is unique, making reconciliation idempotent across repeated polling.
- Fills with non-zero `realizedPnl` create one closed-PnL `trades` row with `source = "exchange_reconciliation"`.
- The closed trade links back to the raw fill through `exchange_fills.trade_id`.
- `trades.exchange_trade_id` and `trades.exchange_order_id` preserve the exchange identifiers used for audit.

## Live Loop Behavior

The live worker already fetches recent account trades for daily loss tracking. That same payload is now passed through `ExchangeReconciliationWorker` after the daily-loss calculation. Persistence failures are logged and swallowed so reconciliation does not stop the trading loop.

## Limitations

- Reconciled closed trades are fill-level records. A partially closed position can produce multiple closed-PnL rows.
- Entry price is inferred from exit fill price, quantity, and realized PnL for one-way USDT-M futures fills.
- The ledger does not yet reconcile order status transitions, cancelled protection orders, or full position lifecycle aggregation.

## Operator Checks

- API: `GET /exchange-fills`
- Metrics: `trading_bot_persisted_records_total{table="exchange_fills"}`
- Database migration: `20260506_0002_exchange_fills`
