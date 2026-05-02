"""Strategy registry for loading trading strategies by config name."""

from __future__ import annotations

from collections.abc import Callable

from app.core.config import Settings
from trading_bot.strategies.base import BaseStrategy
from trading_bot.strategies.ema_rsi_vwap import EmaRsiVwapStrategy

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
        rsi_long_min=settings.rsi_long_min,
        rsi_short_max=settings.rsi_short_max,
        cooldown_candles=settings.cooldown_candles,
    )
