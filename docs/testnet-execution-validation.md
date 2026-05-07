# Testnet Execution Validation

Use this only after a strategy candidate passes offline validation. The current executable candidate is:

```text
session_breakout_ZECUSDT_15m
```

The probe uses Binance USDT-M Futures testnet and the same live execution path as the bot: market entry, reduce-only take-profit, reduce-only stop-loss, order-status polling, recent-fill cost measurement, and cleanup.

## Preconditions

- `USE_TESTNET=true`
- `BINANCE_TESTNET_API_KEY` and `BINANCE_TESTNET_API_SECRET` are set in `.env` or the shell.
- No open ZECUSDT testnet position.
- No open ZECUSDT testnet orders.
- The testnet account has enough USDT test balance for the requested notional.

## Command

```powershell
py main.py testnet-execution-check `
  --symbol ZECUSDT `
  --timeframe 15m `
  --small-notional-usd 10 `
  --max-fee-bps 6 `
  --max-slippage-bps 10
```

The command refuses symbols/timeframes other than `ZECUSDT` and `15m` until another candidate passes the offline promotion gate.

## Pass Criteria

- Entry order succeeds and reaches `FILLED`.
- Stop-loss and take-profit orders are visible after entry.
- Protected order result is marked protected.
- Absolute entry slippage is at or below `10` bps.
- Entry fee is at or below `6` bps when recent fills are available.
- Cleanup leaves no open ZECUSDT position.
- Cleanup leaves no open ZECUSDT orders.

## Reports

Reports are written to:

```text
reports/testnet_execution/latest/testnet_execution_report.json
reports/testnet_execution/latest/testnet_execution_report.md
```

If the probe fails, do not promote the strategy to live trading. Fix the execution issue or reject the strategy if real fills are too expensive for the edge shown in backtests.
