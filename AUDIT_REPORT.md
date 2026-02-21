# Trading Bot — Technical Audit Report (Phase 1)

**Date:** 2025-02-21  
**Scope:** Full codebase audit of `pythonbot` (ZEC/USDT scalper)  
**Files audited:** `zec_scalper.py`, `test_api.py`, `.env` (structure only)

---

## 1. Executive Summary

The project is a **single-file Binance Futures scalper** for ZEC/USDT with EMA/RSI/VWAP/volume entry logic, ATR-based SL/TP, fixed dollar risk, daily loss cap, and Telegram alerts. It is functional but **not production-grade**: monolithic design, one critical position-sizing bug, no backtesting, weak risk/execution separation, and several security/code-quality issues. The codebase is a good candidate for full refactor into a modular, backtestable, production-ready system.

---

## 2. What the Bot Currently Does

| Component | Description |
|-----------|-------------|
| **Asset** | ZEC/USDT perpetual futures (Binance) |
| **Mode** | Live/paper (testnet supported via `USE_TESTNET`) |
| **Entry** | Long: EMA9 > EMA21, close > VWAP, RSI > 48, volume spike (vol > 1.5× 20-period MA), ATR > 0. Short: EMA9 < EMA21, close < VWAP, RSI < 52, same volume/ATR. |
| **Exit** | ATR-based stop loss and take profit placed as reduce-only orders immediately after market entry. |
| **Position** | One position at a time; cooldown = one candle (e.g. 5m = 300s) after a signal. |
| **Risk** | Fixed “risk per trade” in USD, leverage applied; daily loss cap (max loss in USD per day). |
| **Aux** | Symbol info (lot size, tick) from exchange; trades logged to CSV; Telegram alerts and hourly summary. |

---

## 3. Strategy Logic (Summary)

- **Data:** Last 300 candles of configured timeframe (default 5m); indicators computed on full series.
- **Signal bar:** Uses **closed** candle only (`df.iloc[-2]`), so **no repainting** on current candle.
- **Indicators:** EMA(9), EMA(21), RSI(7), ATR(14), VWAP (cumulative over 300 bars), volume 20-period MA.
- **Long:** `ema_fast > ema_slow`, `close > vwap`, `rsi > 48`, `volume > vol_ma * 1.5`, `atr > 0`.
- **Short:** `ema_fast < ema_slow`, `close < vwap`, `rsi < 52`, same volume/ATR.
- **SL/TP:** Stop = close ± ATR×mult (0.8); TP = close ± ATR×mult (1.6). Risk:reward ≈ 1:2.

---

## 4. Architecture Quality

| Aspect | Rating | Notes |
|--------|--------|-------|
| **Modularity** | Poor | Single ~395-line file; strategy, execution, risk, data, and notifications intertwined. |
| **Config** | Partial | .env only; no YAML/structured config; many magic numbers (48, 52, 20) in code. |
| **Testability** | Poor | No unit tests; no backtester; live API required to validate behavior. |
| **Separation of concerns** | Poor | Strategy logic, exchange calls, risk checks, and Telegram in one script. |
| **Dependency injection** | None | Global client and state; hard to swap exchange or strategy. |
| **Error handling** | Basic | Try/except with sleep/retry; no retry decorator or rate-limit handling. |

---

## 5. Performance Issues

- **No backtesting:** Cannot evaluate strategy without live/testnet runs.
- **Repeated exchange info:** `load_symbol_info()` only at startup; fine, but symbol info not cached per symbol if extended to multi-symbol.
- **Full indicator recompute:** Every loop fetches 300 candles and recomputes all indicators; acceptable for 5m, but not scalable for many symbols/timeframes.
- **Telegram:** Synchronous `requests.post` in main loop; could block; no queue or async.
- **Daily PnL:** Fetches up to 500 trades every loop via `update_daily_loss_from_trades()`; heavy under high frequency.

---

## 6. Security Risks

| Risk | Severity | Detail |
|------|----------|--------|
| **API keys in .env** | High | If repo is ever pushed, keys and Telegram token are exposed. Use `.env.example` only; never commit `.env`. |
| **test_api.py** | Critical | **Prints `BINANCE_API_KEY` and `BINANCE_API_SECRET` to stdout.** Must be removed or changed to only check presence. |
| **No secrets validation** | Medium | Script exits if keys missing but does not validate format or testnet vs mainnet. |
| **Telegram token** | High | Same as API keys; must not appear in repo or logs. |

**Recommendation:** Rotate all API keys and Telegram token if `.env` or `test_api.py` output has been committed or shared. Add `.env` to `.gitignore` and provide only `.env.example` with placeholders.

---

## 7. Missing Components

- Backtesting engine  
- Config file (e.g. `config.yaml`) for strategy/risk params  
- Dedicated risk manager module (position size, exposure, drawdown)  
- Execution layer abstraction (order types, retries, idempotency)  
- Performance metrics (Sharpe, Sortino, max DD, win rate, profit factor, expectancy)  
- Unit tests and test structure  
- Logging to file / structured logs  
- Retry and rate-limit handling for Binance API  
- Slippage and fee model for backtests  
- Docker / requirements.txt / setup script  
- CLI (e.g. `backtest` vs `live`)  
- Multi-symbol or portfolio support  

---

## 8. Code Smells

- **Global mutable state:** `LAST_DAILY_RESET`, `DAILY_LOSS`, `LAST_SIGNAL_TS`, `TOTAL_TRADES_TODAY`, `LAST_HOURLY_SUMMARY`, `SYMBOL_INFO`, `LOT_STEP`, `MIN_QTY`, `PRICE_TICK`. Hard to test and reason about.
- **Typo:** `LAST_HOURLLY` (line 291) — unused variable; should be `LAST_HOURLY_SUMMARY` or removed.
- **Magic numbers:** RSI 48/52, vol_ma period 20, 500/200 trade limits, 55-minute summary interval.
- **Mixed responsibilities:** e.g. `hourly_summary()` both sends Telegram and mutates global `LAST_HOURLY_SUMMARY`.
- **Bare `except` in trade loop:** `except Exception` with generic log; some paths could swallow important errors.
- **CSV trades log:** No header row; appends raw rows; fragile for parsing.

---

## 9. Incomplete or Fragile Sections

- **Daily loss tracking:** `update_daily_loss_from_trades()` mixes “overwrite from API” when `realized < 0` with “decrement by profit” when `realized >= 0`. Safer: always set daily loss from API as `max(0, -cumulative_realized_today)`.
- **Market order fill:** Entry uses `res.get('avgPrice')` or `close`; in fast markets fill can be worse; no slippage buffer in size or in backtest.
- **Order failure handling:** If market order fills but SL/TP placement fails, position is open without protection; no reconciliation or retry.
- **Symbol info fallback:** If symbol not in exchange info, globals keep previous symbol’s values; dangerous if symbol is changed at runtime.

---

## 10. Bugs and Logical Errors

### 10.1 Critical: Position sizing (risk per trade)

```python
quote_risk = risk_usd * leverage
qty = quote_risk / dist
```

- **Intended (typical):** “Risk $X per trade” → loss if stop hit = $X → `qty = risk_usd / dist`.
- **Actual:** Loss if stop hit = `qty * dist = risk_usd * leverage` (e.g. $10 × 5 = **$50** per trade).
- **Fix:** For “risk $X in margin (or cash) per trade”, use `qty = risk_usd / dist` (or adjust for margin/leverage as desired and document).

### 10.2 test_api.py prints secrets

- Lines 13–14 print `API_KEY` and `API_SECRET` to console. Must be removed or replaced with “SET”/“NOT SET” only.

### 10.3 Typo

- Line 291: `LAST_HOURLLY` → unused; remove or rename for consistency.

---

## 11. Lookahead and Repainting

- **Repainting:** None on the signal bar; closed candle `iloc[-2]` is used.
- **Lookahead:** Indicators use past and current close only; no future data. VWAP is over the full 300-bar window (not session VWAP); ensure this matches intent.

---

## 12. Risk Management Gaps

- No max drawdown (account-level) check.  
- No per-trade risk-reward validation (e.g. min R:R before placing).  
- No volatility-adjusted cap (e.g. reduce size when ATR is very high).  
- Daily loss is enforced but implemented with the fragile daily-loss logic above.  
- No circuit breaker (e.g. pause after N consecutive losses).  
- No explicit exposure or leverage limit across symbols (single-symbol only today).

---

## 13. Hardcoded and Magic Values

| Location | Value | Suggestion |
|----------|--------|------------|
| RSI long/short | 48, 52 | Move to config/strategy params |
| Volume MA | 20 | Param (e.g. `VOL_MA_LEN`) |
| Hourly summary | 55 min | Config |
| Trade fetch limits | 500, 200 | Constants or config |
| `vol_ma` in indicators | 20 | Same as above |

---

## 14. Structure and Maintainability

- **Single file:** Hard to extend (e.g. new strategy or exchange) without touching core loop.
- **No interfaces:** Strategy and execution are not abstracted; no clear “strategy → signals → risk → execution” pipeline.
- **Imports at top:** Binance client created at module load; no lazy init or env check before creating client.

---

## 15. Recommendations (Pre-Refactor)

1. **Immediate:** Fix position sizing so “risk per trade” matches intended dollar loss; remove or secure `test_api.py`; stop logging or printing any secret.
2. **Before production:** Introduce config (e.g. `config.yaml`), separate strategy / risk / execution, add backtesting, add metrics (Sharpe, max DD, win rate, etc.), and harden daily loss and error handling.
3. **Security:** Add `.env.example`, `.gitignore` for `.env`, and rotate keys if they were ever exposed.

---

*End of Phase 1 Audit. Proceeding to Phase 2–7 will address architecture, strategy improvements, advanced features, production readiness, GitHub layout, and documentation.*
