from __future__ import annotations

import pytest
import pandas as pd

from app.core.config import Settings
from app.strategies.registry import StrategyRegistry, create_default_strategy_registry
from trading_bot.core.types import Signal
from trading_bot.strategies.base import BaseStrategy
from trading_bot.strategies.ema_rsi_vwap import EmaRsiVwapStrategy


def test_default_registry_creates_ema_rsi_vwap_strategy() -> None:
    settings = Settings(ema_fast=4, ema_slow=10)
    registry = create_default_strategy_registry()

    strategy = registry.create("ema-rsi-vwap", settings)

    assert isinstance(strategy, EmaRsiVwapStrategy)
    assert strategy.ema_fast == 4
    assert strategy.ema_slow == 10


def test_registry_rejects_duplicate_names() -> None:
    registry = StrategyRegistry()

    registry.register("custom", lambda settings: _DummyStrategy())

    with pytest.raises(ValueError, match="already registered"):
        registry.register("custom", lambda settings: _DummyStrategy())


def test_registry_reports_unknown_strategy() -> None:
    registry = create_default_strategy_registry()

    with pytest.raises(KeyError, match="Unknown strategy"):
        registry.create("missing", Settings())


class _DummyStrategy(BaseStrategy):
    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        return df

    def get_signal(self, df: pd.DataFrame, **kwargs: object) -> Signal | None:
        return None
