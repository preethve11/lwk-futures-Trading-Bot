# Session Breakout Diagnostics

The `session_breakout` strategy implements the mechanical session-open breakout workflow:

1. Build the high/low range from the two hours before session open.
2. Trade only after the session opens.
3. Enter long above the range high or short below the range low.
4. Set SL at the opposite range boundary.
5. Set TP at 1:1 reward/risk.
6. Take at most one triggered setup per session.

Configured sessions are UTC:

- NSE: `03:45` UTC, equivalent to `09:15` IST.
- London: `08:00` UTC.
- New York: `14:30` UTC.

The strategy is intentionally conservative while research is negative:

- `5m` is disabled by default.
- `session_breakout_min_range_width_pct` defaults to `0.4`.
- `session_breakout_ema_length` defaults to `50`.
- `session_breakout_adx_length` defaults to `14`.
- `session_breakout_min_adx` defaults to `20`.

Run:

```powershell
py main.py backtest --strategy session_breakout --symbol ZECUSDT --timeframe 1h --add-regime-labels --show-rejected
py main.py rejected-signals reports/latest/rejected_signals.json
py main.py strategy-research reports/latest/trade_log.csv --group-by-regime
```

Promotion rule stays unchanged: do not move to testnet/live unless profit factor is at least `1.10` and expectancy is positive.
