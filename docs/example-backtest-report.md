# Example Backtest Report

This is an illustrative report shape. Exact results depend on symbol, timeframe, date range, fees, slippage, and strategy parameters.

## Command

```powershell
py main.py backtest-multi --report-json reports/backtests/example-multi.json
```

Set `SYMBOLS=ZECUSDT,BTCUSDT,ETHUSDT` in `.env` or `strategy.symbols` in `config.yaml` before running.

## Summary

| Metric | Example Value |
| --- | ---: |
| Symbols | 3 |
| Initial capital | 10000.00 |
| Final capital | 10482.35 |
| Total return | 4.82% |
| Total trades | 68 |
| Win rate | 55.88% |
| Profit factor | 1.31 |
| Sharpe | 0.92 |
| Sortino | 1.28 |
| Max drawdown | 7.64% |
| Average R:R | 1.42 |

## Per-Symbol Breakdown

| Symbol | Trades | Return | Win Rate | Profit Factor | Max Drawdown |
| --- | ---: | ---: | ---: | ---: | ---: |
| ZECUSDT | 24 | 2.10% | 58.33% | 1.44 | 4.90% |
| BTCUSDT | 19 | 1.34% | 52.63% | 1.19 | 5.80% |
| ETHUSDT | 25 | 1.38% | 56.00% | 1.29 | 6.20% |

## JSON Shape

```json
{
  "aggregate": {
    "symbol": "MULTI",
    "timeframe": "5m",
    "initial_capital": 10000.0,
    "final_capital": 10482.35,
    "total_pnl": 482.35,
    "total_trades": 68,
    "metrics": {
      "total_return_pct": 4.8235,
      "sharpe_ratio": 0.92,
      "sortino_ratio": 1.28,
      "max_drawdown_pct": 7.64,
      "win_rate": 55.88,
      "profit_factor": 1.31,
      "avg_risk_reward": 1.42
    },
    "equity_curve": [10000.0, 10018.4, 9992.1, 10482.35]
  },
  "symbols": [
    {
      "symbol": "ZECUSDT",
      "timeframe": "5m",
      "initial_capital": 10000.0,
      "final_capital": 10210.0,
      "total_trades": 24
    }
  ]
}
```

## Interpretation Checklist

- Prefer robust results across symbols over one standout symbol.
- Compare train, validation, and out-of-sample performance.
- Use Monte Carlo to estimate drawdown distribution and probability of ruin.
- Check whether the profit factor survives realistic fees and slippage.
- Avoid increasing parameters just to improve a historical result.
