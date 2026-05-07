"""Session-open breakout strategy with diagnostic quality gates."""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import cast

import pandas as pd
from pydantic import BaseModel, Field, field_validator

from trading_bot.analytics.regime import calculate_adx
from trading_bot.core.types import Signal, SignalSide
from trading_bot.strategies.base import BaseStrategy


class SessionOpen(BaseModel):
    """Named UTC session open used by the breakout strategy."""

    name: str = Field(min_length=1)
    open_time_utc: time

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.strip().lower()


class SessionBreakoutStrategy(BaseStrategy):
    """Mechanical pre-session-range breakout with range, EMA, and ADX gates."""

    def __init__(
        self,
        *,
        timeframe: str,
        sessions: list[str],
        pre_open_minutes: int,
        trade_window_minutes: int,
        min_range_width_pct: float,
        ema_length: int,
        adx_length: int,
        min_adx: float,
        entry_buffer_pct: float,
        enabled_timeframes: list[str],
    ) -> None:
        self.timeframe = timeframe.strip().lower()
        self.sessions = [_parse_session(value) for value in sessions]
        self.pre_open_minutes = pre_open_minutes
        self.trade_window_minutes = trade_window_minutes
        self.min_range_width_pct = min_range_width_pct
        self.ema_length = ema_length
        self.adx_length = adx_length
        self.min_adx = min_adx
        self.entry_buffer_pct = entry_buffer_pct
        self.enabled_timeframes = {value.strip().lower() for value in enabled_timeframes}
        self._triggered_sessions: set[str] = set()

    def reset_signal_tracking(self) -> None:
        """Reset diagnostics and one-trade-per-session memory."""
        super().reset_signal_tracking()
        self._triggered_sessions = set()

    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add EMA and ADX columns used by quality gates."""
        enriched = df.copy()
        enriched["ema_50"] = enriched["close"].astype(float).ewm(span=self.ema_length, adjust=False).mean()
        enriched["adx_14"] = calculate_adx(enriched, window=self.adx_length)
        return enriched

    def get_signal(self, df: pd.DataFrame, **kwargs: object) -> Signal | None:
        """Return a breakout signal on the last closed candle, or record a rejection reason."""
        if self.timeframe not in self.enabled_timeframes:
            self.record_rejection("timeframe_disabled")
            return None
        min_bars = max(self.ema_length, self.adx_length * 2, 3)
        if len(df) < min_bars + 2:
            return None

        last = df.iloc[-2]
        last_time = _to_utc_datetime(last["time"])
        active_session = self._active_session(last_time)
        if active_session is None:
            self.record_rejection("outside_session_window")
            return None

        session_open = _session_open_datetime(last_time, active_session)
        session_key = f"{active_session.name}:{session_open.date().isoformat()}"
        if session_key in self._triggered_sessions:
            self.record_rejection("existing_position")
            return None

        pre_session = _pre_session_range(df, session_open, self.pre_open_minutes)
        if pre_session.empty:
            self.record_rejection("invalid_range")
            return None

        range_high = float(pre_session["high"].max())
        range_low = float(pre_session["low"].min())
        if range_high <= range_low or range_low <= 0:
            self.record_rejection("invalid_range")
            return None

        range_width_pct = ((range_high - range_low) / ((range_high + range_low) / 2.0)) * 100.0
        if range_width_pct < self.min_range_width_pct:
            self.record_rejection("range_too_narrow")
            return None

        buffer_mult = self.entry_buffer_pct / 100.0
        buy_trigger = range_high * (1.0 + buffer_mult)
        sell_trigger = range_low * (1.0 - buffer_mult)
        high = float(last["high"])
        low = float(last["low"])
        long_breakout = high >= buy_trigger
        short_breakout = low <= sell_trigger
        if long_breakout == short_breakout:
            self.record_rejection("other")
            return None

        side = SignalSide.LONG if long_breakout else SignalSide.SHORT
        entry = buy_trigger if side == SignalSide.LONG else sell_trigger
        stop = range_low if side == SignalSide.LONG else range_high
        risk = abs(entry - stop)
        if risk <= 0:
            self.record_rejection("invalid_range")
            return None
        take_profit = entry + risk if side == SignalSide.LONG else entry - risk

        ema_value = float(last.get("ema_50", 0.0))
        close = float(last["close"])
        if not _passes_ema_filter(side, close, ema_value):
            self.record_rejection("ema_regime_filter")
            return None

        adx_value = float(last.get("adx_14", 0.0))
        if adx_value < self.min_adx:
            self.record_rejection("adx_chop_filter")
            return None

        self._triggered_sessions.add(session_key)
        return Signal(
            side=side,
            entry_price=entry,
            stop_price=stop,
            take_profit_price=take_profit,
            quantity=0.0,
            timestamp=last_time,
            metadata={
                "range_width_pct": range_width_pct,
                "ema_50": ema_value,
                "adx_14": adx_value,
                "intended_sl_pct": (risk / entry) * 100.0,
                "intended_tp_pct": (risk / entry) * 100.0,
                "session_name": active_session.name,
                "session_open_time_utc": session_open.isoformat(),
            },
        )

    def _active_session(self, current_time: datetime) -> SessionOpen | None:
        for session in self.sessions:
            open_time = _session_open_datetime(current_time, session)
            close_time = open_time + timedelta(minutes=self.trade_window_minutes)
            if open_time <= current_time < close_time:
                return session
        return None


def _parse_session(value: str) -> SessionOpen:
    name, _, raw_time = value.partition(":")
    if not name or not raw_time:
        raise ValueError(f"Invalid session definition: {value}")
    hour_text, _, minute_text = raw_time.partition(":")
    if not hour_text or not minute_text:
        raise ValueError(f"Invalid session open time: {value}")
    return SessionOpen(
        name=name,
        open_time_utc=time(hour=int(hour_text), minute=int(minute_text), tzinfo=timezone.utc),
    )


def _to_utc_datetime(value: object) -> datetime:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    else:
        timestamp = timestamp.tz_convert("UTC")
    return cast(datetime, timestamp.to_pydatetime())


def _session_open_datetime(current_time: datetime, session: SessionOpen) -> datetime:
    return datetime.combine(current_time.date(), session.open_time_utc, tzinfo=timezone.utc)


def _pre_session_range(df: pd.DataFrame, session_open: datetime, minutes: int) -> pd.DataFrame:
    start = session_open - timedelta(minutes=minutes)
    times = pd.to_datetime(df["time"], utc=True)
    return df[(times >= pd.Timestamp(start)) & (times < pd.Timestamp(session_open))]


def _passes_ema_filter(side: SignalSide, close: float, ema_value: float) -> bool:
    if ema_value <= 0:
        return False
    if side == SignalSide.LONG:
        return close > ema_value
    return close < ema_value
