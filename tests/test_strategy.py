from __future__ import annotations

import pandas as pd

from trading_bot.core.types import SignalSide
from trading_bot.strategies.ema_rsi_vwap import EmaRsiVwapStrategy


def _ohlcv(closes: list[float], volumes: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "time": pd.date_range("2026-01-01", periods=len(closes), freq="5min", tz="UTC"),
            "open": closes,
            "high": [value + 1 for value in closes],
            "low": [value - 1 for value in closes],
            "close": closes,
            "volume": volumes,
        }
    )


def _fast_strategy() -> EmaRsiVwapStrategy:
    return EmaRsiVwapStrategy(
        ema_fast=2,
        ema_slow=3,
        rsi_len=2,
        atr_len=2,
        atr_stop_mult=1.0,
        atr_tp_mult=2.0,
        vol_mult=1.0,
        vol_ma_len=2,
        rsi_long_min=40,
        rsi_short_max=60,
        cooldown_candles=1,
    )


def test_strategy_generates_long_signal_from_closed_candle() -> None:
    strategy = _fast_strategy()
    df = _ohlcv(
        closes=[100, 101, 102, 103, 104, 106, 107],
        volumes=[100, 100, 100, 100, 100, 1000, 50],
    )

    enriched = strategy.compute_indicators(df)
    signal = strategy.get_signal(enriched)

    assert signal is not None
    assert signal.side == SignalSide.LONG
    assert signal.entry_price == 106
    assert signal.stop_price < signal.entry_price
    assert signal.take_profit_price > signal.entry_price
    assert signal.quantity == 0.0
    assert signal.metadata["atr"] > 0


def test_strategy_generates_short_signal_from_closed_candle() -> None:
    strategy = _fast_strategy()
    df = _ohlcv(
        closes=[110, 109, 108, 107, 106, 104, 103],
        volumes=[100, 100, 100, 100, 100, 1000, 50],
    )

    enriched = strategy.compute_indicators(df)
    signal = strategy.get_signal(enriched)

    assert signal is not None
    assert signal.side == SignalSide.SHORT
    assert signal.entry_price == 104
    assert signal.stop_price > signal.entry_price
    assert signal.take_profit_price < signal.entry_price


def test_strategy_ignores_unclosed_current_candle() -> None:
    strategy = _fast_strategy()
    df = _ohlcv(
        closes=[100, 101, 102, 103, 104, 105, 120],
        volumes=[100, 100, 100, 100, 100, 100, 5000],
    )

    enriched = strategy.compute_indicators(df)
    signal = strategy.get_signal(enriched)

    assert signal is None


def test_strategy_returns_none_when_history_is_too_short() -> None:
    strategy = _fast_strategy()
    df = _ohlcv(closes=[100, 101, 102], volumes=[100, 100, 100])

    enriched = strategy.compute_indicators(df)

    assert strategy.get_signal(enriched) is None
