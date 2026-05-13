"""Adaptive momentum breakout strategy with crowding and exchange-stress gates."""

from __future__ import annotations

from datetime import datetime
from typing import cast

import numpy as np
import pandas as pd

from trading_bot.analytics.regime import calculate_adx
from trading_bot.core.types import Signal, SignalSide
from trading_bot.risk.crowding import CrowdingSnapshot, CrowdingThresholds, evaluate_crowding
from trading_bot.strategies.base import BaseStrategy


class AdaptiveMomentumBreakoutStrategy(BaseStrategy):
    """Donchian momentum breakout strategy guarded by cost, crowding, and regime filters."""

    def __init__(
        self,
        *,
        symbol: str,
        timeframe: str,
        enabled_timeframes: list[str],
        donchian_window: int = 20,
        ema_fast: int = 50,
        ema_slow: int = 200,
        adx_length: int = 14,
        long_adx_min: float = 22.0,
        short_adx_min: float = 25.0,
        volume_ratio_min: float = 1.1,
        atr_length: int = 14,
        stop_atr_mult: float = 2.5,
        take_profit_r_multiple: float = 2.0,
        trailing_stop_atr_mult: float = 3.0,
        max_holding_bars: int = 120,
        spread_max_bps: float = 8.0,
        funding_rate_abs_long_max: float = 0.0003,
        funding_rate_abs_short_max: float = 0.0003,
        funding_rate_delta_max: float = 0.0001,
        open_interest_spike_pct_max: float = 12.0,
        adl_quantile_max: float = 3.0,
        liquidation_spike_ratio_max: float = 3.0,
        volatility_shock_percentile_min: float = 0.9,
        allowed_days_of_week: list[int] | None = None,
        blocked_hours_utc: list[int] | None = None,
        fee_bps: float = 4.0,
        slippage_bps: float = 5.0,
        max_expected_cost_share: float = 0.35,
        short_position_size_multiplier: float = 0.5,
        cooldown_candles: int = 1,
    ) -> None:
        self.symbol = symbol.strip().upper()
        self.timeframe = timeframe.strip().lower()
        self.enabled_timeframes = {value.strip().lower() for value in enabled_timeframes}
        self.donchian_window = donchian_window
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.adx_length = adx_length
        self.long_adx_min = long_adx_min
        self.short_adx_min = short_adx_min
        self.volume_ratio_min = volume_ratio_min
        self.atr_length = atr_length
        self.stop_atr_mult = stop_atr_mult
        self.take_profit_r_multiple = take_profit_r_multiple
        self.trailing_stop_atr_mult = trailing_stop_atr_mult
        self.max_holding_bars = max_holding_bars
        self.spread_max_bps = spread_max_bps
        self.thresholds = CrowdingThresholds(
            funding_rate_abs_long_max=funding_rate_abs_long_max,
            funding_rate_abs_short_max=funding_rate_abs_short_max,
            funding_rate_delta_max=funding_rate_delta_max,
            open_interest_spike_pct_max=open_interest_spike_pct_max,
            adl_quantile_max=adl_quantile_max,
            liquidation_spike_ratio_max=liquidation_spike_ratio_max,
            volatility_shock_percentile_min=volatility_shock_percentile_min,
        )
        self.allowed_days_of_week = set(range(7)) if allowed_days_of_week is None else set(allowed_days_of_week)
        self.blocked_hours_utc = set(blocked_hours_utc or [])
        self.fee_bps = fee_bps
        self.slippage_bps = slippage_bps
        self.max_expected_cost_share = max_expected_cost_share
        self.short_position_size_multiplier = short_position_size_multiplier
        self.cooldown_candles = cooldown_candles

    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add lookahead-safe Donchian, trend, volatility, funding, and OI features."""
        enriched = df.copy().sort_values("time").reset_index(drop=True)
        enriched["time"] = pd.to_datetime(enriched["time"], utc=True)
        for column in ["open", "high", "low", "close", "volume"]:
            enriched[column] = enriched[column].astype(float)

        close = enriched["close"]
        high = enriched["high"]
        low = enriched["low"]
        volume = enriched["volume"]
        true_range = pd.concat(
            [
                high - low,
                (high - close.shift(1)).abs(),
                (low - close.shift(1)).abs(),
            ],
            axis=1,
        ).max(axis=1)
        volume_ma = volume.rolling(20, min_periods=5).mean()
        returns = close.pct_change()
        realized_vol = returns.rolling(100, min_periods=20).std()

        enriched["atr_14"] = true_range.rolling(self.atr_length, min_periods=self.atr_length).mean()
        enriched["atr"] = enriched["atr_14"]
        enriched["ema_50"] = close.ewm(span=self.ema_fast, adjust=False).mean()
        enriched["ema_200"] = close.ewm(span=self.ema_slow, adjust=False).mean()
        enriched["adx_14"] = calculate_adx(enriched, window=self.adx_length)
        enriched["volume_ratio_20"] = volume / volume_ma.replace(0, np.nan)
        enriched["spread_proxy_bps"] = ((high - low) / close.replace(0, np.nan)) * 10_000.0
        enriched["donchian_high"] = high.rolling(self.donchian_window, min_periods=self.donchian_window).max().shift(1)
        enriched["donchian_low"] = low.rolling(self.donchian_window, min_periods=self.donchian_window).min().shift(1)
        enriched["volatility_percentile_100"] = _rolling_percentile(realized_vol, window=100)
        enriched["day_of_week"] = enriched["time"].dt.dayofweek
        enriched["hour_of_day"] = enriched["time"].dt.hour
        enriched["trend_state"] = np.where(enriched["adx_14"] >= self.long_adx_min, "TRENDING", "RANGING")

        funding_rate = _optional_series(enriched, "funding_rate", default=0.0)
        funding_delta_bars = _bars_for_eight_hours(self.timeframe)
        enriched["funding_rate"] = funding_rate
        enriched["funding_rate_delta_8h"] = funding_rate - funding_rate.shift(funding_delta_bars).fillna(funding_rate)
        open_interest = _optional_series(enriched, "open_interest", default=0.0)
        enriched["open_interest"] = open_interest
        enriched["open_interest_change_pct"] = _pct_change(open_interest, periods=funding_delta_bars)
        force_notional = _optional_series(enriched, "force_order_notional", default=0.0)
        force_ma = force_notional.rolling(96, min_periods=10).mean().replace(0, np.nan)
        enriched["liquidation_spike_ratio"] = (force_notional / force_ma).fillna(0.0)
        enriched["adl_quantile"] = _optional_series(enriched, "adl_quantile", default=0.0)
        return enriched

    def get_signal(self, df: pd.DataFrame, **kwargs: object) -> Signal | None:
        """Return the last closed breakout signal, or record the first blocking reason."""
        if self.timeframe not in self.enabled_timeframes:
            self.record_rejection("timeframe_disabled")
            return None
        min_bars = max(self.donchian_window, self.ema_slow, self.atr_length * 2, self.adx_length * 2) + 3
        if len(df) < min_bars:
            return None

        last = df.iloc[-2]
        close = _row_float(last, "close")
        atr = _row_float(last, "atr_14")
        donchian_high = _row_float(last, "donchian_high")
        donchian_low = _row_float(last, "donchian_low")
        if close <= 0 or atr <= 0 or donchian_high <= 0 or donchian_low <= 0:
            self.record_rejection("other")
            return None

        if _row_float(last, "spread_proxy_bps") > self.spread_max_bps:
            self.record_rejection("spread_too_wide")
            return None
        day_of_week = int(_row_float(last, "day_of_week", default=-1.0))
        hour_of_day = int(_row_float(last, "hour_of_day", default=-1.0))
        if day_of_week not in self.allowed_days_of_week or hour_of_day in self.blocked_hours_utc:
            self.record_rejection("time_filter")
            return None

        long_breakout = close > donchian_high
        short_breakout = close < donchian_low
        if long_breakout == short_breakout:
            self.record_rejection("no_breakout")
            return None
        side = SignalSide.LONG if long_breakout else SignalSide.SHORT

        ema_fast = _row_float(last, "ema_50")
        ema_slow = _row_float(last, "ema_200")
        if not _passes_ema_regime(side, ema_fast, ema_slow):
            self.record_rejection("no_trend_confirmation")
            return None
        adx = _row_float(last, "adx_14")
        required_adx = self.long_adx_min if side == SignalSide.LONG else self.short_adx_min
        if adx < required_adx:
            self.record_rejection("adx_chop_filter")
            return None
        if _row_float(last, "volume_ratio_20") < self.volume_ratio_min:
            self.record_rejection("volume_too_low")
            return None

        crowding = evaluate_crowding(_crowding_snapshot(last), self.thresholds, side=side)
        if crowding.blocked:
            self.record_rejection(crowding.reasons[0])
            return None

        risk_distance = atr * self.stop_atr_mult
        if risk_distance <= 0:
            self.record_rejection("other")
            return None
        take_profit_distance = risk_distance * self.take_profit_r_multiple
        expected_edge_bps = (take_profit_distance / close) * 10_000.0
        expected_cost_bps = _expected_cost_bps(
            side=side,
            fee_bps=self.fee_bps,
            slippage_bps=self.slippage_bps,
            funding_rate=_row_float(last, "funding_rate"),
        )
        if expected_edge_bps <= 0 or expected_cost_bps > expected_edge_bps * self.max_expected_cost_share:
            self.record_rejection("cost_gate")
            return None

        stop = close - risk_distance if side == SignalSide.LONG else close + risk_distance
        take_profit = close + take_profit_distance if side == SignalSide.LONG else close - take_profit_distance
        timestamp = _to_datetime(last["time"])
        return Signal(
            side=side,
            entry_price=close,
            stop_price=stop,
            take_profit_price=take_profit,
            quantity=0.0,
            timestamp=timestamp,
            metadata={
                "strategy_id": f"adaptive_momentum_breakout_{self.symbol}_{self.timeframe}",
                "atr_14": atr,
                "ema_50": ema_fast,
                "ema_200": ema_slow,
                "adx_14": adx,
                "donchian_high": donchian_high,
                "donchian_low": donchian_low,
                "volume_ratio_20": _row_float(last, "volume_ratio_20"),
                "spread_proxy_bps": _row_float(last, "spread_proxy_bps"),
                "funding_rate": _row_float(last, "funding_rate"),
                "funding_rate_delta_8h": _row_float(last, "funding_rate_delta_8h"),
                "open_interest_change_pct": _row_float(last, "open_interest_change_pct"),
                "adl_quantile": _row_float(last, "adl_quantile"),
                "liquidation_spike_ratio": _row_float(last, "liquidation_spike_ratio"),
                "expected_edge_bps": expected_edge_bps,
                "expected_cost_bps": expected_cost_bps,
                "day_of_week": day_of_week,
                "hour_of_day": hour_of_day,
                "intended_sl_pct": (risk_distance / close) * 100.0,
                "intended_tp_pct": (take_profit_distance / close) * 100.0,
                "trailing_stop_atr_mult": self.trailing_stop_atr_mult,
                "max_holding_bars": self.max_holding_bars,
                "exit_on_ema50_cross": True,
                "exit_on_ranging_regime": True,
                "position_size_multiplier": self.short_position_size_multiplier if side == SignalSide.SHORT else 1.0,
            },
        )


def _passes_ema_regime(side: SignalSide, ema_fast: float, ema_slow: float) -> bool:
    if ema_fast <= 0 or ema_slow <= 0:
        return False
    if side == SignalSide.LONG:
        return ema_fast > ema_slow
    return ema_fast < ema_slow


def _expected_cost_bps(*, side: SignalSide, fee_bps: float, slippage_bps: float, funding_rate: float) -> float:
    funding_bps = funding_rate * 10_000.0
    adverse_funding_bps = max(funding_bps, 0.0) if side == SignalSide.LONG else max(-funding_bps, 0.0)
    return (fee_bps * 2.0) + (slippage_bps * 2.0) + adverse_funding_bps


def _crowding_snapshot(row: pd.Series) -> CrowdingSnapshot:
    return CrowdingSnapshot(
        funding_rate=_row_float(row, "funding_rate"),
        funding_rate_delta_8h=_row_float(row, "funding_rate_delta_8h"),
        open_interest_change_pct=_row_float(row, "open_interest_change_pct"),
        adl_quantile=_row_float(row, "adl_quantile"),
        liquidation_spike_ratio=_row_float(row, "liquidation_spike_ratio"),
        volatility_percentile=_row_float(row, "volatility_percentile_100"),
    )


def _optional_series(df: pd.DataFrame, column: str, *, default: float) -> pd.Series:
    if column in df:
        return df[column].astype(float).fillna(default)
    return pd.Series(default, index=df.index, dtype=float)


def _pct_change(series: pd.Series, *, periods: int) -> pd.Series:
    previous = series.shift(periods).replace(0, np.nan)
    return (((series - previous) / previous) * 100.0).replace([np.inf, -np.inf], np.nan).fillna(0.0)


def _bars_for_eight_hours(timeframe: str) -> int:
    normalized = timeframe.strip().lower()
    if normalized.endswith("m"):
        minutes = int(normalized[:-1])
        return max(1, int(480 / minutes))
    if normalized.endswith("h"):
        hours = int(normalized[:-1])
        return max(1, int(8 / hours))
    return 8


def _rolling_percentile(series: pd.Series, *, window: int) -> pd.Series:
    def percentile(values: pd.Series) -> float:
        latest = values.iloc[-1]
        if pd.isna(latest):
            return 0.0
        return float((values <= latest).mean())

    return series.rolling(window, min_periods=max(10, window // 5)).apply(percentile, raw=False).fillna(0.0)


def _row_float(row: pd.Series, column: str, *, default: float = 0.0) -> float:
    if column not in row:
        return default
    value = row[column]
    if pd.isna(value):
        return default
    if isinstance(value, (int, float, np.integer, np.floating)):
        return float(value)
    try:
        return float(str(value))
    except ValueError:
        return default


def _to_datetime(value: object) -> datetime:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    else:
        timestamp = timestamp.tz_convert("UTC")
    return cast(datetime, timestamp.to_pydatetime())
