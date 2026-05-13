from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from app.core.config import Settings
from app.strategies.registry import create_default_strategy_registry
from trading_bot.core.types import SignalSide
from trading_bot.risk.correlation import Exposure, would_exceed_correlated_exposure
from trading_bot.risk.crowding import CrowdingSnapshot, CrowdingThresholds, evaluate_crowding
from trading_bot.risk.drawdown_pause import evaluate_drawdown_pause
from trading_bot.strategies.adaptive_momentum_breakout import AdaptiveMomentumBreakoutStrategy


def _candles(rows: int = 230) -> pd.DataFrame:
    values = []
    for index in range(rows):
        close = 100.0 + index * 0.05
        volume = 1_000.0
        if index == rows - 2:
            volume = 2_000.0
        values.append(
            {
                "time": pd.Timestamp("2026-01-01T00:00:00Z") + pd.Timedelta(hours=index),
                "open": close - 0.01,
                "high": close + 0.02,
                "low": close - 0.02,
                "close": close,
                "volume": volume,
                "funding_rate": 0.0,
                "open_interest": 1_000_000.0 + index,
                "adl_quantile": 0.0,
                "force_order_notional": 0.0,
            }
        )
    return pd.DataFrame(values)


def _strategy() -> AdaptiveMomentumBreakoutStrategy:
    return AdaptiveMomentumBreakoutStrategy(
        symbol="BTCUSDT",
        timeframe="1h",
        enabled_timeframes=["15m", "1h"],
        spread_max_bps=8.0,
        volume_ratio_min=1.1,
        max_expected_cost_share=0.8,
    )


def test_adaptive_momentum_breakout_generates_long_signal_with_diagnostics() -> None:
    strategy = _strategy()
    enriched = strategy.compute_indicators(_candles())

    signal = strategy.get_signal(enriched)

    assert signal is not None
    assert signal.side == SignalSide.LONG
    assert signal.metadata["strategy_id"] == "adaptive_momentum_breakout_BTCUSDT_1h"
    assert float(signal.metadata["expected_edge_bps"]) > float(signal.metadata["expected_cost_bps"])
    assert signal.metadata["day_of_week"] == 5


def test_adaptive_momentum_blocks_funding_delta_spike() -> None:
    strategy = _strategy()
    candles = _candles()
    candles.loc[len(candles) - 2, "funding_rate"] = 0.00025
    enriched = strategy.compute_indicators(candles)

    signal = strategy.get_signal(enriched)

    assert signal is None
    assert strategy.rejected_signals["funding_delta_spike"] == 1


def test_adaptive_momentum_blocks_open_interest_spike() -> None:
    strategy = _strategy()
    candles = _candles()
    candles.loc[: len(candles) - 10, "open_interest"] = 1_000_000.0
    candles.loc[len(candles) - 2, "open_interest"] = 1_300_000.0
    enriched = strategy.compute_indicators(candles)

    signal = strategy.get_signal(enriched)

    assert signal is None
    assert strategy.rejected_signals["open_interest_spike"] == 1


def test_crowding_filter_prioritizes_market_stress_reason() -> None:
    decision = evaluate_crowding(
        CrowdingSnapshot(
            funding_rate_delta_8h=0.0002,
            open_interest_change_pct=20.0,
            volatility_percentile=0.95,
        ),
        CrowdingThresholds(),
        side=SignalSide.LONG,
    )

    assert decision.blocked is True
    assert "market_stress" in decision.reasons


def test_correlation_cap_blocks_shared_crypto_risk_on_exposure() -> None:
    blocked = would_exceed_correlated_exposure(
        [Exposure(symbol="BTCUSDT", side=SignalSide.LONG, equity_pct=25.0)],
        candidate_symbol="ETHUSDT",
        candidate_side=SignalSide.LONG,
        candidate_equity_pct=10.0,
        correlations={("BTCUSDT", "ETHUSDT"): 0.9},
        max_correlated_equity_pct=30.0,
    )

    assert blocked is True


def test_drawdown_pause_triggers_manual_review_window() -> None:
    decision = evaluate_drawdown_pause(
        [10_000.0, 10_500.0, 9_600.0],
        threshold_pct=8.0,
        as_of=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    assert decision.paused is True
    assert decision.resume_after is not None
    assert decision.resume_after.hour == 0


def test_registry_creates_adaptive_momentum_breakout_strategy() -> None:
    settings = Settings(strategy_name="adaptive_momentum_breakout", symbol="BTCUSDT", timeframe="1h")

    strategy = create_default_strategy_registry().create("adaptive-momentum-breakout", settings)

    assert isinstance(strategy, AdaptiveMomentumBreakoutStrategy)
