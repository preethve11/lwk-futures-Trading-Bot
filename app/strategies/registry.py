"""Strategy registry for loading trading strategies by config name."""

from __future__ import annotations

from collections.abc import Callable

from app.core.config import Settings
from trading_bot.strategies.base import BaseStrategy
from trading_bot.strategies.ema_rsi_vwap import EmaRsiVwapStrategy
from trading_bot.strategies.ema_rsi_vwap_combined import EmaRsiVwapCombinedStrategy
from trading_bot.strategies.ema_rsi_vwap_high_vol import EmaRsiVwapHighVolStrategy
from trading_bot.strategies.ema_rsi_vwap_trend_only import EmaRsiVwapTrendOnlyStrategy
from trading_bot.strategies.session_breakout import SessionBreakoutStrategy

StrategyFactory = Callable[[Settings], BaseStrategy]


class StrategyRegistry:
    """In-memory registry of strategy factories."""

    def __init__(self) -> None:
        self._factories: dict[str, StrategyFactory] = {}

    def register(self, name: str, factory: StrategyFactory) -> None:
        normalized = self._normalize(name)
        if normalized in self._factories:
            raise ValueError(f"Strategy already registered: {normalized}")
        self._factories[normalized] = factory

    def create(self, name: str, settings: Settings) -> BaseStrategy:
        normalized = self._normalize(name)
        try:
            factory = self._factories[normalized]
        except KeyError as exc:
            available = ", ".join(sorted(self._factories)) or "none"
            raise KeyError(f"Unknown strategy '{name}'. Available strategies: {available}") from exc
        return factory(settings)

    def names(self) -> list[str]:
        return sorted(self._factories)

    @staticmethod
    def _normalize(name: str) -> str:
        return name.strip().lower().replace("-", "_")


def create_default_strategy_registry() -> StrategyRegistry:
    registry = StrategyRegistry()
    registry.register("ema_rsi_vwap", _create_ema_rsi_vwap)
    registry.register("ema_rsi_vwap_trend_only", _create_ema_rsi_vwap_trend_only)
    registry.register("ema_rsi_vwap_high_vol", _create_ema_rsi_vwap_high_vol)
    registry.register("ema_rsi_vwap_combined", _create_ema_rsi_vwap_combined)
    registry.register("session_breakout", _create_session_breakout)
    return registry


def _create_ema_rsi_vwap(settings: Settings) -> EmaRsiVwapStrategy:
    return EmaRsiVwapStrategy(
        ema_fast=settings.ema_fast,
        ema_slow=settings.ema_slow,
        rsi_len=settings.rsi_len,
        atr_len=settings.atr_len,
        atr_stop_mult=settings.atr_stop_mult,
        atr_tp_mult=settings.atr_tp_mult,
        vol_mult=settings.vol_mult,
        vol_ma_len=settings.vol_ma_len,
        vwap_window=settings.vwap_window,
        rsi_long_min=settings.rsi_long_min,
        rsi_short_max=settings.rsi_short_max,
        cooldown_candles=settings.cooldown_candles,
    )


def _create_ema_rsi_vwap_trend_only(settings: Settings) -> EmaRsiVwapTrendOnlyStrategy:
    return EmaRsiVwapTrendOnlyStrategy(
        ema_fast=settings.ema_fast,
        ema_slow=settings.ema_slow,
        rsi_len=settings.rsi_len,
        atr_len=settings.atr_len,
        atr_stop_mult=settings.atr_stop_mult,
        atr_tp_mult=settings.atr_tp_mult,
        vol_mult=settings.vol_mult,
        vol_ma_len=settings.vol_ma_len,
        vwap_window=settings.vwap_window,
        rsi_long_min=settings.rsi_long_min,
        rsi_short_max=settings.rsi_short_max,
        cooldown_candles=settings.cooldown_candles,
    )


def _create_ema_rsi_vwap_high_vol(settings: Settings) -> EmaRsiVwapHighVolStrategy:
    return EmaRsiVwapHighVolStrategy(
        ema_fast=settings.ema_fast,
        ema_slow=settings.ema_slow,
        rsi_len=settings.rsi_len,
        atr_len=settings.atr_len,
        atr_stop_mult=settings.atr_stop_mult,
        atr_tp_mult=settings.atr_tp_mult,
        vol_mult=settings.vol_mult,
        vol_ma_len=settings.vol_ma_len,
        vwap_window=settings.vwap_window,
        rsi_long_min=settings.rsi_long_min,
        rsi_short_max=settings.rsi_short_max,
        cooldown_candles=settings.cooldown_candles,
    )


def _create_ema_rsi_vwap_combined(settings: Settings) -> EmaRsiVwapCombinedStrategy:
    return EmaRsiVwapCombinedStrategy(
        ema_fast=settings.ema_fast,
        ema_slow=settings.ema_slow,
        rsi_len=settings.rsi_len,
        atr_len=settings.atr_len,
        atr_stop_mult=settings.atr_stop_mult,
        atr_tp_mult=settings.atr_tp_mult,
        vol_mult=settings.vol_mult,
        vol_ma_len=settings.vol_ma_len,
        vwap_window=settings.vwap_window,
        rsi_long_min=settings.rsi_long_min,
        rsi_short_max=settings.rsi_short_max,
        cooldown_candles=settings.cooldown_candles,
    )


def _create_session_breakout(settings: Settings) -> SessionBreakoutStrategy:
    return SessionBreakoutStrategy(
        timeframe=settings.timeframe,
        sessions=settings.session_breakout_sessions,
        pre_open_minutes=settings.session_breakout_pre_open_minutes,
        trade_window_minutes=settings.session_breakout_trade_window_minutes,
        min_range_width_pct=settings.session_breakout_min_range_width_pct,
        ema_length=settings.session_breakout_ema_length,
        adx_length=settings.session_breakout_adx_length,
        min_adx=settings.session_breakout_min_adx,
        entry_buffer_pct=settings.session_breakout_entry_buffer_pct,
        enabled_timeframes=settings.session_breakout_enabled_timeframes,
    )
