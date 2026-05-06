# Week 2 Monte Carlo Simulation

The Monte Carlo simulator estimates forward risk by resampling historical trade PnLs with replacement.

It reports:

- probability of ruin using a configurable drawdown threshold
- final-capital distribution
- total-return distribution
- max-drawdown distribution
- p05/p50/p95 confidence intervals

Run from an explicit JSON input:

```powershell
python main.py monte-carlo --returns-json reports/backtests/multi_symbol_latest.json
```

Supported JSON input shapes:

```json
[10.5, -4.2, 8.0]
```

```json
{"pnls": [10.5, -4.2, 8.0]}
```

```json
{"returns": [0.001, -0.0004, 0.0008]}
```

```json
{"aggregate": {"equity_curve": [10000, 10010.5, 10006.3, 10014.3]}}
```

If `--returns-json` is omitted, the CLI reads recent persisted trades for the configured `SYMBOL` from the configured database.

Useful overrides:

```env
MONTE_CARLO_SIMULATIONS=1000
MONTE_CARLO_HORIZON_TRADES=100
MONTE_CARLO_RUIN_DRAWDOWN_PCT=30
MONTE_CARLO_RANDOM_SEED=42
MONTE_CARLO_REPORT_DIR=reports/monte_carlo
```

The simulator is advisory only. It never places orders, changes strategy parameters, or mutates live trading state.
