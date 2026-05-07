# Strategy Research Diagnostics

The `strategy-research` command analyzes closed simulated trades and explains why a strategy is failing before more optimization or live testing.

It is designed for paper-validation outputs such as:

```powershell
py main.py strategy-research --trades-csv reports/paper_validation/<run_id>/trade_log.csv
```

If `--trades-csv` is omitted, the command uses the newest local `reports/paper_validation/*/trade_log.csv` file.

Outputs:

- `strategy_research.json`
- `strategy_research.md`

## What It Measures

- Total PnL, win rate, profit factor, expectancy, median trade PnL, average R:R
- Grouped performance by run, symbol, timeframe, market condition, entry hour, and exit reason
- Transaction-cost drag by timeframe
- Largest winners and largest losers
- Whether losses are broad-based or concentrated in a few outliers

## Questions It Answers

- Why is `BTCUSDT_5m` worse than other configs?
- Is the 5m timeframe too noisy or too expensive after fees?
- Are all timeframes underperforming?
- Are losses caused by a few large losers or consistent small negative trades?

## Operating Rule

Do not optimize blindly after a failed backtest. Run `strategy-research`, disable clearly failing symbol/timeframe buckets, then re-run walk-forward optimization only on candidates with plausible positive expectancy.

The command is analytical only. It does not place orders, mutate live settings, or bypass the strategy performance gate.
