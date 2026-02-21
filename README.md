# Trading Bot

Modular, production-grade algorithmic trading bot for Binance USDT-M Futures. Supports backtesting and live trading with configurable risk management and performance analytics.

---

## Project Overview

This bot implements a **scalping strategy** (EMA + RSI + VWAP + volume spike) with:

- **Strategy:** Long when EMA(9) > EMA(21), price > VWAP, RSI > 48, volume spike; Short with opposite conditions. ATR-based stop loss and take profit.
- **Risk:** Fixed dollar risk per trade (loss at stop = `RISK_PER_TRADE_USD`), daily loss cap, max drawdown, min risk-reward, optional ATR position cap.
- **Execution:** Binance Futures (testnet and live), retry on rate limit, SL/TP orders placed with market entry.

The codebase is structured for **hedge-fund level quality**: clean architecture, strategy/execution/risk separation, backtesting with slippage and fees, performance metrics (Sharpe, Sortino, max drawdown, win rate, profit factor, expectancy), and production features (config, logging, Docker, CLI).

---

## Strategy Explanation

- **Indicators:** EMA(9), EMA(21), RSI(7), ATR(14), VWAP (over lookback), volume 20-period MA.
- **Entry (long):** EMA fast > EMA slow, close > VWAP, RSI > 48, volume > 1.5× vol_ma, ATR > 0.
- **Entry (short):** EMA fast < EMA slow, close < VWAP, RSI < 52, same volume/ATR filter.
- **Exit:** Stop loss = entry ± ATR×0.8; Take profit = entry ± ATR×1.6 (configurable).
- **Signal bar:** Uses **closed candle only** (no repainting).

---

## Installation

### Requirements

- Python 3.10+
- pip

### Steps

1. **Clone and enter the project**
   ```bash
   cd pythonbot
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate   # Linux/macOS
   # or: venv\Scripts\activate  # Windows
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configuration (local only — safe for GitHub)**
   - Copy `.env.example` to `.env` (`.env` is in `.gitignore` and is **never** committed).
   - **Option A:** Set `BINANCE_API_KEY` and `BINANCE_API_SECRET`; set `USE_TESTNET=true` for demo or `false` for live.
   - **Option B (recommended):** Set `BINANCE_TESTNET_API_KEY` / `BINANCE_TESTNET_API_SECRET` (from [Binance Testnet](https://testnet.binancefuture.com)) and `BINANCE_MAINNET_API_KEY` / `BINANCE_MAINNET_API_SECRET` (from Binance → API Management). Toggle `USE_TESTNET=true` or `false` to switch without editing keys.
   - Optionally set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` for alerts.
   - Adjust `config.yaml` for strategy/risk/execution (or use env overrides).

---

## Configuration Guide

- **`.env`** — Local secrets only (never commit). API keys, `USE_TESTNET`, `SYMBOL`, `TIMEFRAME`, `LEVERAGE`, `RISK_PER_TRADE_USD`, `MAX_DAILY_LOSS_USD`, Telegram. Use `.env.example` as the template; it is safe to commit.
- **`config.yaml`** — Strategy (EMA/RSI/ATR/VWAP params), risk (caps, min R:R), execution (leverage, slippage/fee for backtest), logging, backtest dates and initial capital.

Env vars override `config.yaml` for the same keys.

---

## How to Run Backtest

```bash
python main.py backtest [--config path/to/config.yaml]
```

- Fetches klines from Binance (using API keys in `.env`).
- Runs the strategy with slippage and fee simulation.
- Prints: total trades, return %, Sharpe, Sortino, max drawdown, win rate, profit factor, expectancy.

---

## How to Run Live Trading

```bash
python main.py live [--config path/to/config.yaml]
```

- Connects to Binance Futures (testnet if `USE_TESTNET=true`).
- Sets leverage and loads symbol filters.
- Main loop: check daily loss cap → fetch klines → compute indicators → generate signal → risk check → place market + SL/TP.
- Sends Telegram alerts on entry and hourly summary (if configured).
- Use **testnet first** and small `RISK_PER_TRADE_USD`.

---

## Troubleshooting

- **`APIError(code=-2015): Invalid API-key, IP, or permissions`**  
  Binance returns this when:
  - The API key does **not** have **Enable Futures** (or **Enable USDT-M Futures**) checked. Create a new key or edit the key and enable Futures.
  - You are using a **mainnet** key while `USE_TESTNET=true` (or the opposite). Use a key created on [Binance Testnet](https://testnet.binancefuture.com) for testnet.
  - The key has **IP access restrictions** and your current IP (`157.51.142.3` or similar) is not in the allow list. Add your IP or disable the restriction.

- **Backtest: "Daily loss cap reached" many times**  
  Fixed: the backtest now resets daily loss at the start of each new calendar day, so the cap applies per day, not over the whole run.

---

## Risk Disclaimer

Trading futures involves substantial risk of loss. This software is for educational and research purposes. Past backtest results do not guarantee future performance. Use testnet before live trading. Never risk more than you can afford to lose. The authors are not responsible for any financial losses.

---

## Performance Metrics Explained

| Metric | Description |
|--------|-------------|
| **Sharpe Ratio** | Risk-adjusted return (excess return per unit of volatility). Higher is better. |
| **Sortino Ratio** | Like Sharpe but uses downside deviation only. |
| **Max Drawdown** | Largest peak-to-trough decline (%). |
| **Win Rate** | Fraction of trades with positive PnL. |
| **Profit Factor** | Gross profit / gross loss. >1 is profitable. |
| **Expectancy** | Average PnL per trade (USD). |

---

## Example Results (Backtest)

After running `python main.py backtest` you will see output similar to:

```
--- Backtest Results ---
Total trades: 42 (wins: 24, losses: 18)
Total return: 5.32%
Sharpe ratio: 0.89
Sortino ratio: 1.12
Max drawdown: 8.45%
Win rate: 57.1%
Profit factor: 1.35
Expectancy: 12.50 USD/trade
```

(Exact numbers depend on symbol, timeframe, and history.)

---

## Roadmap

- [ ] Multi-symbol / portfolio mode
- [ ] Walk-forward optimization runner (using `trading_bot/backtesting/walk_forward.py`)
- [ ] Monte Carlo report (using `trading_bot/analytics/monte_carlo.py`)
- [ ] Trailing stop (logic in risk; execution support)
- [ ] Optional async execution and websocket streams

---

## Contribution Guide

1. Fork the repo.
2. Create a feature branch. Follow existing style (type hints, docstrings, no secrets in code).
3. Add/update tests under `tests/`.
4. Run tests: `pytest tests/`.
5. Submit a pull request.

---

## Folder Structure

```
trading_bot/
  core/           # Config, types, logging
  strategies/     # Base + EMA/RSI/VWAP strategy
  risk/           # Position sizing, daily loss, drawdown
  execution/      # Exchange abstraction + Binance Futures
  backtesting/    # Engine, walk-forward
  analytics/      # Metrics, Monte Carlo
  utils/          # Telegram, timeframes, exchange filters
main.py           # CLI: backtest | live
config.yaml
.env.example
requirements.txt
Dockerfile
README.md
AUDIT_REPORT.md
ARCHITECTURE.md
```

See **ARCHITECTURE.md** for how components fit together and how to add strategies, deploy, and avoid overfitting.
