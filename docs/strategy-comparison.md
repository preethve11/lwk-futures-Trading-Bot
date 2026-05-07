# Strategy Comparison

Use `strategy-compare` to run one baseline and one or more variants across the same symbol/timeframe datasets.

```powershell
py main.py strategy-compare `
  --baseline ema_rsi_vwap `
  --variants ema_rsi_vwap_trend_only ema_rsi_vwap_high_vol ema_rsi_vwap_combined `
  --symbols ZECUSDT BTCUSDT ETHUSDT `
  --timeframes 1h 15m `
  --output-dir reports/strategy_comparison/latest
```

Outputs:

- `strategy_comparison.json`
- `strategy_comparison.md`

Rank candidates by positive expectancy first, then profit factor and Sharpe. A comparison winner is not automatically live-ready; it still has to pass the live promotion gate and out-of-sample validation.
