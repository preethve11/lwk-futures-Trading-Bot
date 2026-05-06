# Week 2 Walk-Forward Optimizer

The walk-forward optimizer tunes EMA/RSI/ATR/VWAP strategy parameters with Optuna on sliding train windows, then validates the best parameter set on the following out-of-sample window.

Run from a CSV:

```powershell
HISTORICAL_DATA_CSV=data/ZECUSDT_5m.csv python main.py walk-forward
```

Run from a per-symbol historical data directory:

```powershell
HISTORICAL_DATA_DIR=data python main.py walk-forward
```

Useful environment overrides:

```env
WALK_FORWARD_TRAIN_SIZE=500
WALK_FORWARD_VALIDATION_SIZE=100
WALK_FORWARD_STEP_SIZE=100
WALK_FORWARD_TRIALS=30
WALK_FORWARD_OBJECTIVE=sharpe
WALK_FORWARD_REPORT_DIR=reports/optimizations
```

Supported objectives:

- `sharpe`
- `sortino`
- `total_return`
- `profit_factor`
- `win_rate`

The JSON report includes every train/validation window, best parameters, train score, out-of-sample score, overfit score, validation metrics, aggregate out-of-sample metrics, and the generated timestamp.

The optimizer is advisory only. It does not mutate live trading settings, place orders, or change persisted bot state.
