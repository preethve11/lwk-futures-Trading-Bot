"""
EMA + RSI + VWAP + volume spike strategy (ZEC scalper logic).
Uses closed candle only (iloc[-2]) to avoid repainting.
"""

from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, Any

import numpy as np
import pandas as pd

from trading_bot.core.types import Signal, SignalSide
from trading_bot.strategies.base import BaseStrategy


class EmaRsiVwapStrategy(BaseStrategy):
    """
    Long: EMA_fast > EMA_slow, close > VWAP, RSI > rsi_long_min, volume spike, ATR > 0.
    Short: EMA_fast < EMA_slow, close < VWAP, RSI < rsi_short_max, volume spike, ATR > 0.
    SL/TP from ATR multiples.
    """

    def __init__(
        self,
        ema_fast: int = 9,
        ema_slow: int = 21,
        rsi_len: int = 7,
        atr_len: int = 14,
        atr_stop_mult: float = 0.8,
        atr_tp_mult: float = 1.6,
        vol_mult: float = 1.5,
        vol_ma_len: int = 20,
        rsi_long_min: float = 48,
        rsi_short_max: float = 52,
        cooldown_candles: int = 1,
    ):
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.rsi_len = rsi_len
        self.atr_len = atr_len
        self.atr_stop_mult = atr_stop_mult
        self.atr_tp_mult = atr_tp_mult
        self.vol_mult = vol_mult
        self.vol_ma_len = vol_ma_len
        self.rsi_long_min = rsi_long_min
        self.rsi_short_max = rsi_short_max
        self.cooldown_candles = cooldown_candles

    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        # VWAP (cumulative over series)
        typ = (df["high"] + df["low"] + df["close"]) / 3.0
        pv = (typ * df["volume"]).cumsum()
        cumv = df["volume"].cumsum()
        df["vwap"] = pv / cumv.replace(0, np.nan).bfill()
        df["ema_fast"] = df["close"].ewm(span=self.ema_fast, adjust=False).mean()
        df["ema_slow"] = df["close"].ewm(span=self.ema_slow, adjust=False).mean()
        # RSI
        delta = df["close"].diff()
        up = delta.clip(lower=0)
        down = (-delta).clip(lower=0)
        rs = up.rolling(self.rsi_len).mean() / down.rolling(self.rsi_len).mean().replace(0, np.nan)
        df["rsi"] = 100 - (100 / (1 + rs))
        # ATR
        high_low = df["high"] - df["low"]
        high_close = (df["high"] - df["close"].shift()).abs()
        low_close = (df["low"] - df["close"].shift()).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df["atr"] = tr.rolling(self.atr_len).mean()
        df["vol_ma"] = df["volume"].rolling(self.vol_ma_len).mean()
        return df

    def get_signal(self, df: pd.DataFrame, **kwargs: Any) -> Optional[Signal]:
        """
        Uses last closed bar (iloc[-2]) to avoid repainting.
        Returns raw signal with quantity=0; caller must set quantity via risk manager.
        """
        if len(df) < max(self.ema_slow, self.atr_len, self.vol_ma_len) + 2:
            return None
        last = df.iloc[-2]
        close = float(last["close"])
        ema_f = float(last["ema_fast"])
        ema_s = float(last["ema_slow"])
        rsi = float(last["rsi"]) if not pd.isna(last["rsi"]) else 50.0
        atr = float(last["atr"]) if not pd.isna(last["atr"]) else 0.0
        vwap = float(last["vwap"])
        vol = float(last["volume"])
        vol_ma = float(last["vol_ma"]) if not pd.isna(last["vol_ma"]) else vol
        vol_spike = vol > (vol_ma * self.vol_mult)
        if atr <= 0 or not vol_spike:
            return None
        ema_bull = ema_f > ema_s
        ema_bear = ema_f < ema_s
        long_ok = ema_bull and close > vwap and rsi > self.rsi_long_min
        short_ok = ema_bear and close < vwap and rsi < self.rsi_short_max
        if not (long_ok or short_ok):
            return None
        side = SignalSide.LONG if long_ok else SignalSide.SHORT
        stop = close - atr * self.atr_stop_mult if side == SignalSide.LONG else close + atr * self.atr_stop_mult
        tp = close + atr * self.atr_tp_mult if side == SignalSide.LONG else close - atr * self.atr_tp_mult
        return Signal(
            side=side,
            entry_price=close,
            stop_price=stop,
            take_profit_price=tp,
            quantity=0.0,  # Caller sets via risk_manager.validate_signal
            timestamp=datetime.now(timezone.utc),
            metadata={"atr": atr, "rsi": rsi},
        )
