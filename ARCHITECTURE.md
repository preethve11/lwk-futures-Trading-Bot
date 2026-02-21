# Architecture & Usage Guide (Phase 7)

This document explains how the trading bot is built, how to extend it, and how to use it safely.

---

## 1. How the Architecture Works

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐     ┌────────────┐
│   Config    │────▶│   Strategy   │────▶│ RiskManager │────▶│ Execution  │
│ (yaml+env)  │     │ (indicators  │     │ (size, caps)│     │ (exchange) │
└─────────────┘     │  + signal)   │     └─────────────┘     └────────────┘
                    └──────────────┘
```

- **Config** — Single source of truth: `config.yaml` + `.env`. Strategy params, risk limits, API keys (env only).
- **Strategy** — Pure logic: given OHLCV, compute indicators and return a **raw signal** (entry, stop, tp, side). No quantity (that’s risk’s job).
- **RiskManager** — Validates signal (min R:R, daily loss, drawdown) and **computes quantity** so that loss at stop = `risk_per_trade_usd`.
- **Execution** — Fetches klines, symbol info, places market + SL/TP. Retries on rate limit.

**Backtest path:** Config → load klines → Strategy.compute_indicators + get_signal → RiskManager.validate_signal → BacktestEngine runs bar-by-bar, applies slippage/fees, records trades → Analytics (Sharpe, Sortino, MDD, etc.).

**Live path:** Same flow in a loop; ExecutionClient replaces the engine for real orders.

---

## 2. How Strategies Plug In

1. Implement **`BaseStrategy`** in `trading_bot/strategies/`:
   - `compute_indicators(df)` — add columns (e.g. EMA, RSI, ATR). No lookahead.
   - `get_signal(df)` — from **closed bar only** (e.g. `df.iloc[-2]`), return `Optional[Signal]` with entry, stop, tp, side, and `quantity=0`.
2. The **caller** (live loop or backtest engine) calls `risk_manager.validate_signal(...)` to get allowed quantity and attaches it to the signal.
3. Register your strategy in `main.py` (backtest and live) by instantiating it with config params and passing it to the engine or loop.

Strategy must **not** use future data and must **not** depend on execution (only on OHLCV and optional kwargs like `equity` if you pass it).

---

## 3. How Risk Management Works

- **Position size:** `quantity = risk_per_trade_usd / |entry - stop|`. So if stop is hit, loss in USD = `risk_per_trade_usd`. (No leverage multiplier on risk; leverage only affects margin.)
- **Daily loss cap:** `set_daily_loss(...)` from exchange trades; `check_daily_loss()` blocks new trades if cap reached.
- **Max drawdown:** `set_equity(...)`; if `(peak - current) / peak` ≥ `max_drawdown_pct`, new trades blocked.
- **Min risk-reward:** Signal’s (tp - entry) / (entry - stop) must be ≥ `min_risk_reward`.
- **Min notional:** `quantity * entry` must be ≥ `min_notional`.
- **ATR cap (optional):** In very high volatility (e.g. ATR > 5% of price), size is reduced so positions don’t blow up.

All of this is in `trading_bot/risk/manager.py`. Execution and strategy only see “allowed + quantity” or “rejected + reason”.

---

## 4. How to Add New Strategies

1. Add a new file under `trading_bot/strategies/`, e.g. `my_strategy.py`.
2. Subclass `BaseStrategy`, implement `compute_indicators` and `get_signal` (return raw signal with `quantity=0`).
3. In `main.py`, add a switch or config key to choose strategy (e.g. `strategy: ema_rsi_vwap` vs `my_strategy`), instantiate the right class from config, and pass it to the backtest engine or live loop.
4. Backtest first; then run on testnet.

---

## 5. How to Deploy

- **Local:** `python main.py live` (with `.env` and `config.yaml`). Use a process manager (e.g. systemd, PM2) or run in a screen/tmux.
- **Docker:** Build with `docker build -t trading-bot .`. Run with `-e` or mount `.env`:  
  `docker run --env-file .env trading-bot` (default CMD is `live`). Override: `docker run --env-file .env trading-bot python main.py backtest`.
- **Secrets:** Never put API keys in code or in `config.yaml`. Use `.env` (and ensure `.env` is in `.gitignore`). In CI/CD, use secret manager or env vars only.

---

## 6. How to Optimize

- **Parameter tuning:** Change strategy/risk params in `config.yaml` (or env), run backtest, compare metrics. Prefer **walk-forward**: train on one period, test on a later period (see `trading_bot/backtesting/walk_forward.py`).
- **Monte Carlo:** Use `trading_bot/analytics/monte_carlo.py` to shuffle trade PnLs and see distribution of returns and max drawdowns; helps assess robustness.
- **Avoid overfitting:** Use out-of-sample test windows, fewer parameters, and simple rules. If backtest is great but walk-forward or Monte Carlo is weak, the strategy is likely overfit.

---

## 7. How to Backtest Properly

- **No lookahead:** Strategy must use only data up to the **previous closed bar** when generating a signal for the current bar. Our engine uses `df.iloc[:i]` and strategy uses closed bar; no future data.
- **Slippage and fees:** Backtest applies `slippage_bps` and `fee_bps` to entry/exit. Set them in config to match reality.
- **Realistic sizing:** Risk manager uses the same formula in backtest as in live (risk_usd / stop distance). No “perfect” fills.
- **Interpret metrics:** Sharpe, Sortino, max DD, win rate, profit factor, and expectancy are in `trading_bot/analytics/metrics.py`. Use them together; don’t optimize one number in isolation.

---

## 8. How to Avoid Overfitting

- Use **train/test** or **walk-forward** splits; never tune on the same period you report results on.
- Prefer **fewer, interpretable** parameters (e.g. ATR mult, RSI levels) over many free parameters.
- Run **Monte Carlo** on trade PnLs; if the distribution of outcomes is wide or often negative, the edge may be fragile.
- Test on **multiple symbols or timeframes**; if it only works on one, it may be curve-fit.
- Keep **risk management** strict (daily loss, max DD) so that one bad streak doesn’t invalidate the test.

---

*For the full list of issues and fixes from the original codebase, see **AUDIT_REPORT.md**.*
