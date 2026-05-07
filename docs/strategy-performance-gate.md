# Strategy Performance Gate

The strategy performance gate blocks live promotion when the latest persisted backtest does not meet minimum profitability and risk criteria.

This does not guarantee future profit. Its purpose is to prevent obviously weak, stale, under-sampled, or over-risked strategy configurations from reaching live trading.

## Command

```powershell
py main.py strategy-gate
```

For CI or local smoke output without failing the shell:

```powershell
py main.py strategy-gate --allow-failures
```

## Live Enforcement

Mainnet live trading enforces the gate by default:

```env
LIVE_STRATEGY_GATE_REQUIRED_FOR_MAINNET=true
```

Testnet/live research can opt into the same enforcement:

```env
LIVE_STRATEGY_GATE_ENABLED=true
```

## Thresholds

```env
LIVE_GATE_MIN_TRADES=20
LIVE_GATE_MIN_PROFIT_FACTOR=1.1
LIVE_GATE_MIN_EXPECTANCY_USD=0
LIVE_GATE_MIN_SHARPE=0
LIVE_GATE_MAX_DRAWDOWN_PCT=20
LIVE_GATE_MAX_BACKTEST_AGE_DAYS=30
```

Recommended production tightening after enough testnet history:

- require at least 50 to 100 trades
- require positive out-of-sample expectancy
- require profit factor above 1.2 to 1.4
- require max drawdown below the operator's funded-account tolerance
- prefer walk-forward and multi-symbol validation over a single backtest
- run Monte Carlo before increasing notional size

## API And Dashboard

- `GET /risk/performance-gate`
- The Risk Controls dashboard shows the latest gate status, source backtest run, and key metrics.

## Operational Rule

Do not bypass a failed gate for mainnet. If the gate fails, either improve validation evidence or reduce the system back to testnet/paper mode.
