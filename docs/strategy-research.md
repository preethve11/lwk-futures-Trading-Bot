# Strategy Research Diagnostics

The `strategy-research` command analyzes closed simulated trades and explains why a strategy is failing before more optimization or live testing.

It is designed for paper-validation outputs such as:

```powershell
py main.py strategy-research --trades-csv reports/paper_validation/<run_id>/trade_log.csv
```

If `--trades-csv` is omitted, the command uses the newest local `reports/paper_validation/*/trade_log.csv` file.

To generate a fresh adaptive momentum breakout research report from local symbol/timeframe CSVs:

```powershell
py main.py strategy-research-runner --strategy adaptive_momentum_breakout --symbols BTCUSDT ETHUSDT SOLUSDT BNBUSDT LINKUSDT --timeframes 1h 15m --group-by-regime
```

For a timestamped paper-validation report:

```powershell
py main.py paper-validation --strategy adaptive_momentum_breakout --symbols BTCUSDT ETHUSDT SOLUSDT BNBUSDT LINKUSDT --timeframes 1h 15m --group-by-regime
```

Outputs:

- `strategy_research.json`
- `strategy_research.md`

## What It Measures

- Total PnL, win rate, profit factor, expectancy, median trade PnL, average R:R
- Grouped performance by run, symbol, timeframe, market condition, entry hour, and exit reason
- Transaction-cost drag by timeframe
- Funding, funding-delta, open-interest, ADL, liquidation, spread, and expected cost/edge diagnostics when present in trade logs
- Day-of-week and hour-of-day timing buckets
- Symbol PnL concentration for the 50% promotion-cap check
- Largest winners and largest losers
- Whether losses are broad-based or concentrated in a few outliers

## Questions It Answers

- Why is `BTCUSDT_5m` worse than other configs?
- Is the 5m timeframe too noisy or too expensive after fees?
- Are all timeframes underperforming?
- Are losses caused by a few large losers or consistent small negative trades?
- Are trades being filtered by funding/OI/ADL/liquidation stress gates?
- Are specific days or UTC hours materially better out of sample?
- Is PnL concentrated in one symbol rather than diversified across candidates?

## Operating Rule

Do not optimize blindly after a failed backtest. Run `strategy-research`, disable clearly failing symbol/timeframe buckets, then re-run walk-forward optimization only on candidates with plausible positive expectancy.

The command is analytical only. It does not place orders, mutate live settings, or bypass the strategy performance gate.
