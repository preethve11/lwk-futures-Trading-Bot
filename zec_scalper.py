#!/usr/bin/env python3
"""
ZEC/USDT Scalper v3 — production-ready features:
- EMA9/EMA21 + RSI7 + VWAP + vol spike entry
- ATR-based SL/TP
- Fixed $ risk per trade with leverage
- Single concurrent position + cooldown
- Min notional & lot-step rounding using exchange info
- Realized PnL capture -> updates DAILY_LOSS (daily cap enforced)
- Telegram alerts + hourly summary
- Testnet-first (USE_TESTNET=true)
"""

from __future__ import annotations
import os, time, math, logging, json
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Tuple, Any

import numpy as np
import pandas as pd
from dotenv import load_dotenv
import requests

from binance.client import Client
from binance.exceptions import BinanceAPIException

# -------------------------
# Load .env
# -------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(HERE, ".env")
if not os.path.exists(ENV_PATH):
    raise SystemExit(f".env not found at {ENV_PATH}")
load_dotenv(ENV_PATH)

API_KEY = os.getenv("BINANCE_API_KEY", "").strip()
API_SECRET = os.getenv("BINANCE_API_SECRET", "").strip()
USE_TESTNET = os.getenv("USE_TESTNET", "true").lower() == "true"
SYMBOL = os.getenv("SYMBOL", "ZECUSDT").strip().upper()
LEVERAGE = int(os.getenv("LEVERAGE", "5"))
RISK_PER_TRADE_USD = float(os.getenv("RISK_PER_TRADE_USD", "10.0"))
TIMEFRAME = os.getenv("TIMEFRAME", "5m")
MIN_NOTIONAL = float(os.getenv("MIN_NOTIONAL", "5.0"))
MAX_DAILY_LOSS_USD = float(os.getenv("MAX_DAILY_LOSS_USD", "50"))

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

# strategy params
EMA_FAST = int(os.getenv("EMA_FAST", "9"))
EMA_SLOW = int(os.getenv("EMA_SLOW", "21"))
RSI_LEN = int(os.getenv("RSI_LEN", "7"))
ATR_LEN = int(os.getenv("ATR_LEN", "14"))
ATR_STOP_MULT = float(os.getenv("ATR_STOP_MULT", "0.8"))
ATR_TP_MULT = float(os.getenv("ATR_TP_MULT", "1.6"))
VOL_MULT = float(os.getenv("VOL_MULT", "1.5"))
COOLDOWN_CANDLES = int(os.getenv("COOLDOWN_CANDLES", "1"))

# runtime state
LAST_DAILY_RESET = datetime.now(timezone.utc).date()
DAILY_LOSS = 0.0
LAST_SIGNAL_TS = 0.0
TOTAL_TRADES_TODAY = 0
LAST_HOURLY_SUMMARY = datetime.now(timezone.utc)

# logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("zec_scalper_v3")

# validate keys
if not API_KEY or not API_SECRET:
    raise SystemExit("Missing API keys in .env")

# init client
client = Client(API_KEY, API_SECRET)
if USE_TESTNET:
    client.API_URL = "https://testnet.binancefuture.com/fapi"
    logger.info("Using Futures TESTNET endpoint")
else:
    logger.info("Using Futures LIVE endpoint")

# -------------------------
# Helpers: Telegram & utils
# -------------------------
def tg_send(text: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.debug("TG not configured: %s", text[:120])
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code != 200:
            logger.warning("Telegram send failed: %s %s", r.status_code, r.text)
    except Exception as e:
        logger.exception("Telegram error: %s", e)

def tf_minutes(tf: str) -> int:
    if tf.endswith('m'): return int(tf[:-1])
    if tf.endswith('h'): return int(tf[:-1]) * 60
    if tf.endswith('d'): return int(tf[:-1]) * 60 * 24
    raise ValueError("unsupported timeframe")

# -------------------------
# Exchange info: step size, minQty, lot rounding
# -------------------------
SYMBOL_INFO: Optional[dict] = None
LOT_STEP = 0.0001
MIN_QTY = 0.001
PRICE_TICK = 0.01

def load_symbol_info(symbol: str):
    global SYMBOL_INFO, LOT_STEP, MIN_QTY, PRICE_TICK
    try:
        info = client.futures_exchange_info()
        for s in info.get("symbols", []):
            if s.get("symbol") == symbol:
                SYMBOL_INFO = s
                break
        if SYMBOL_INFO is None:
            logger.warning("Symbol info not found for %s; using defaults", symbol)
            return
        # find lotSize and price filter
        for f in SYMBOL_INFO.get("filters", []):
            if f.get("filterType") == "LOT_SIZE":
                MIN_QTY = float(f.get("minQty", MIN_QTY))
                LOT_STEP = float(f.get("stepSize", LOT_STEP))
            if f.get("filterType") == "PRICE_FILTER":
                PRICE_TICK = float(f.get("tickSize", PRICE_TICK))
        logger.info("Loaded symbol info: minQty=%.6f step=%.6f tick=%.6f", MIN_QTY, LOT_STEP, PRICE_TICK)
    except Exception as e:
        logger.exception("Failed to load symbol info: %s", e)

def round_qty(qty: float) -> float:
    # round down to step size
    if qty <= 0:
        return 0.0
    step = LOT_STEP
    rounded = math.floor(qty / step) * step
    # respect min qty
    if rounded < MIN_QTY:
        return 0.0
    return float(round(rounded, 8))

def round_price(price: float) -> float:
    tick = PRICE_TICK
    return float(round(round(price / tick) * tick, 8))

# -------------------------
# Market data & indicators
# -------------------------
def get_klines(symbol: str, interval: str, limit: int = 300) -> pd.DataFrame:
    raw = client.futures_klines(symbol=symbol, interval=interval, limit=limit)
    df = pd.DataFrame(raw, columns=[
        "open_time","open","high","low","close","volume","close_time","quote_av","num_trades","tb_base_av","tb_quote_av","ignore"
    ])
    df[['open','high','low','close','volume']] = df[['open','high','low','close','volume']].astype(float)
    df['time'] = pd.to_datetime(df['open_time'], unit='ms')
    return df[['time','open','high','low','close','volume']]

def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df['typ'] = (df['high'] + df['low'] + df['close']) / 3.0
    df['pv'] = (df['typ'] * df['volume']).cumsum()
    df['cumv'] = df['volume'].cumsum()
    df['vwap'] = df['pv'] / df['cumv']
    df['ema_fast'] = df['close'].ewm(span=EMA_FAST, adjust=False).mean()
    df['ema_slow'] = df['close'].ewm(span=EMA_SLOW, adjust=False).mean()
    delta = df['close'].diff()
    up = delta.clip(lower=0); down = (-delta).clip(lower=0)
    df['rsi'] = 100 - (100/(1 + (up.rolling(RSI_LEN).mean().div(down.rolling(RSI_LEN).mean().replace(0, np.nan)))))
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['atr'] = tr.rolling(ATR_LEN).mean()
    df['vol_ma'] = df['volume'].rolling(20).mean()
    return df

# -------------------------
# Position helpers
# -------------------------
def get_open_position(symbol: str) -> Optional[dict]:
    try:
        pos_info = client.futures_position_information(symbol=symbol)
        for p in pos_info:
            if float(p.get('positionAmt', 0.0)) != 0:
                return p
        return None
    except Exception as e:
        logger.exception("get_open_position error: %s", e)
        return None

def calculate_qty(entry_price: float, stop_price: float, risk_usd: float, leverage: int) -> float:
    dist = abs(entry_price - stop_price)
    if dist <= 0: return 0.0
    quote_risk = risk_usd * leverage
    qty = quote_risk / dist
    qty = round_qty(qty)
    return qty

def place_market_and_orders(side: str, qty: float, stop_price: float, tp_price: float) -> Tuple[Optional[dict], Optional[dict], Optional[dict]]:
    try:
        # place market
        res = client.futures_create_order(symbol=SYMBOL, side=side, type='MARKET', quantity=str(qty))
        logger.info("Market order placed: %s qty=%.6f", side, qty)
        # place TP and SL (reduceOnly)
        if side == 'BUY':
            tp = client.futures_create_order(symbol=SYMBOL, side='SELL', type='LIMIT', timeInForce='GTC',
                                            quantity=str(qty), price=str(round_price(tp_price)), reduceOnly=True)
            sl = client.futures_create_order(symbol=SYMBOL, side='SELL', type='STOP_MARKET',
                                            stopPrice=str(round_price(stop_price)), closePosition=False, quantity=str(qty), reduceOnly=True)
        else:
            tp = client.futures_create_order(symbol=SYMBOL, side='BUY', type='LIMIT', timeInForce='GTC',
                                            quantity=str(qty), price=str(round_price(tp_price)), reduceOnly=True)
            sl = client.futures_create_order(symbol=SYMBOL, side='BUY', type='STOP_MARKET',
                                            stopPrice=str(round_price(stop_price)), closePosition=False, quantity=str(qty), reduceOnly=True)
        return res, sl, tp
    except Exception as e:
        logger.exception("place_market_and_orders error: %s", e)
        return None, None, None

# -------------------------
# Realized PnL capture and logging
# -------------------------
TRADES_LOG = os.path.join(HERE, "trades_log.csv")

def log_trade(timestamp: str, side: str, qty: float, entry: float, sl: float, tp: float, note: str = ""):
    row = f"{timestamp},{side},{qty},{entry},{sl},{tp},{note}\n"
    with open(TRADES_LOG, "a") as f:
        f.write(row)

def fetch_recent_trades(symbol: str, limit: int = 100) -> list:
    try:
        return client.futures_account_trades(symbol=symbol, limit=limit)
    except Exception as e:
        logger.exception("fetch_recent_trades error: %s", e)
        return []

def update_daily_loss_from_trades():
    """
    Fetch recent trades, sum realized PnL for today and update DAILY_LOSS.
    This function is conservative: reads fills and sums negative realized PnL.
    """
    global DAILY_LOSS, LAST_DAILY_RESET
    # reset daily if needed
    now_date = datetime.now(timezone.utc).date()
    if now_date != LAST_DAILY_RESET:
        LAST_DAILY_RESET = now_date
        DAILY_LOSS = 0.0
    trades = fetch_recent_trades(SYMBOL, limit=500)
    day_start_ts = int(datetime.combine(now_date, datetime.min.time(), tzinfo=timezone.utc).timestamp() * 1000)
    realized = 0.0
    for t in trades:
        # t has keys: symbol, id, orderId, price, qty, quoteQty, commission, commissionAsset, time, realizedPnl, buyer, maker, ...
        try:
            if int(t.get("time", 0)) >= day_start_ts:
                rp = float(t.get("realizedPnl", 0.0))
                realized += rp
        except Exception:
            continue
    # realized is net PnL (positive or negative) for today across trades
    # We care about losses: if realized < 0, add abs to DAILY_LOSS
    if realized < 0:
        DAILY_LOSS = -realized
    else:
        # if realized positive, ensure DAILY_LOSS doesn't incorrectly include older losses
        DAILY_LOSS = max(0.0, DAILY_LOSS - realized) if DAILY_LOSS > 0 else 0.0

# -------------------------
# Safety helpers
# -------------------------
def check_daily_loss() -> bool:
    update_daily_loss_from_trades()
    if DAILY_LOSS >= MAX_DAILY_LOSS_USD:
        msg = f"[ALERT] Daily loss cap reached: ${DAILY_LOSS:.2f} >= ${MAX_DAILY_LOSS_USD}"
        logger.warning(msg); tg_send(msg)
        return False
    return True

# -------------------------
# Hourly summary
# -------------------------
def hourly_summary():
    global LAST_HOURLY_SUMMARY
    now = datetime.now(timezone.utc)
    if (now - LAST_HOURLY_SUMMARY) < timedelta(minutes=55):
        return
    LAST_HOURLLY = LAST_HOURLY_SUMMARY  # minor local var to avoid linter
    # compute basic stats
    trades = fetch_recent_trades(SYMBOL, limit=200)
    total_trades = len(trades)
    pnl = sum(float(t.get("realizedPnl", 0.0)) for t in trades)
    open_pos = get_open_position(SYMBOL)
    pos_info = f"Open position: {open_pos.get('positionAmt')} at {open_pos.get('entryPrice')}" if open_pos else "No open position"
    msg = f"Hourly summary for {SYMBOL}:\nTotal recent trades: {total_trades}\nNet realized PnL (recent): {pnl:.4f} USDT\n{pos_info}\nDaily loss tracked: ${DAILY_LOSS:.2f}"
    tg_send(msg)
    LAST_HOURLY_SUMMARY = now

# -------------------------
# Main loop (core)
# -------------------------
def main():
    global LAST_SIGNAL_TS, TOTAL_TRADES_TODAY

    # load symbol info and set leverage
    load_symbol_info(SYMBOL)
    try:
        client.futures_change_leverage(symbol=SYMBOL, leverage=LEVERAGE)
        logger.info("Leverage set to %sx", LEVERAGE)
    except Exception as e:
        logger.warning("Could not set leverage: %s", e)

    tg_send(f"Scalper v3 starting for {SYMBOL} (testnet={USE_TESTNET}) with leverage {LEVERAGE}x")

    cooldown_s = tf_minutes(TIMEFRAME) * 60

    while True:
        try:
            if not check_daily_loss():
                time.sleep(60)
                continue

            df = get_klines(SYMBOL, TIMEFRAME, limit=300)
            df = compute_indicators(df)
            # use closed candle (-2 because -1 is current still-building)
            last = df.iloc[-2]
            close = float(last['close']); ema_f = float(last['ema_fast']); ema_s = float(last['ema_slow'])
            rsi = float(last['rsi']) if not pd.isna(last['rsi']) else 50.0
            atr = float(last['atr']) if not pd.isna(last['atr']) else 0.0
            vwap = float(last['vwap']); vol = float(last['volume']); vol_ma = float(last['vol_ma']) if not pd.isna(last['vol_ma']) else vol

            pos = get_open_position(SYMBOL)
            if pos and abs(float(pos.get('positionAmt', 0))) > 0:
                logger.info("Position open, waiting... entry=%s amt=%s", pos.get('entryPrice'), pos.get('positionAmt'))
                # still update PnL from trades
                update_daily_loss_from_trades()
                hourly_summary()
                time.sleep(5)
                continue

            now_ts = time.time()
            if now_ts - LAST_SIGNAL_TS < cooldown_s:
                time.sleep(1); continue

            # signals
            ema_bull = ema_f > ema_s; ema_bear = ema_f < ema_s
            vol_spike = vol > (vol_ma * VOL_MULT)
            long_signal = ema_bull and close > vwap and rsi > 48 and vol_spike and atr > 0
            short_signal = ema_bear and close < vwap and rsi < 52 and vol_spike and atr > 0

            if long_signal or short_signal:
                LAST_SIGNAL_TS = now_ts
                side = 'BUY' if long_signal else 'SELL'
                stop_price = close - atr * ATR_STOP_MULT if side == 'BUY' else close + atr * ATR_STOP_MULT
                tp_price = close + atr * ATR_TP_MULT if side == 'BUY' else close - atr * ATR_TP_MULT

                qty = calculate_qty(close, stop_price, RISK_PER_TRADE_USD, LEVERAGE)
                if qty <= 0:
                    logger.warning("qty computed 0; skip")
                    tg_send("qty computed 0 — increase risk or change params")
                    time.sleep(1); continue
                notional = qty * close
                if notional < MIN_NOTIONAL:
                    logger.warning("notional too small $%.3f < min %.3f", notional, MIN_NOTIONAL)
                    tg_send(f"Order notional too small (${notional:.2f}). Increase account/risk.")
                    time.sleep(1); continue

                # place orders
                res, sl, tp = place_market_and_orders(side, qty, stop_price, tp_price)
                if res:
                    # record
                    entry_price = float(res.get('avgPrice') or close)
                    log_trade(datetime.now(timezone.utc).isoformat(), side, qty, entry_price, stop_price, tp_price, note="entry")
                    TOTAL_TRADES_TODAY += 1
                    tg_send(f"Entered {side} {SYMBOL} qty={qty} entry={entry_price:.3f} SL={stop_price:.3f} TP={tp_price:.3f}")
                else:
                    logger.warning("order placement failed")
            # periodic housekeeping
            update_daily_loss_from_trades()
            hourly_summary()
            time.sleep(1)

        except KeyboardInterrupt:
            logger.info("User shutdown")
            tg_send("Scalper v3 shutting down (user request).")
            break
        except BinanceAPIException as e:
            logger.exception("Binance APIException: %s", e)
            tg_send(f"Binance API error: {e}")
            time.sleep(5)
        except Exception as e:
            logger.exception("Unexpected error: %s", e)
            tg_send(f"Unexpected error in scalper v3: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
