from __future__ import annotations

import pandas as pd
from sqlalchemy import select

from app.persistence.database import create_session_factory, init_db, session_scope
from app.persistence.models import (
    BacktestResultModel,
    ExecutionModel,
    FeatureModel,
    MarketDataModel,
    PerformanceHealthModel,
    PortfolioAllocationModel,
    RegimeModel,
    StrategyModel,
    SystemLogModel,
)
from app.persistence.repositories import (
    BacktestResultRepository,
    ExecutionRepository,
    FeatureRepository,
    MarketDataRepository,
    PerformanceHealthRepository,
    PortfolioAllocationRepository,
    RegimeRepository,
    StrategyMetadataRepository,
    SystemLogRepository,
)
from trading_bot.data.database import persist_feature_frame, persist_market_data, persist_regime_frame
from trading_bot.data.market_data import clean_ohlcv
from trading_bot.execution.smart_order_router import SmartOrderRouter
from trading_bot.features.feature_library import build_feature_frame
from trading_bot.monitoring.performance_tracker import PerformanceHealthTracker, StrategyHealthStatus
from trading_bot.portfolio.meta_allocator import EqualWeightMetaAllocator, StrategyHealthInput
from trading_bot.regime.regime_detector import add_professional_regime_labels


def _candles(rows: int = 140) -> pd.DataFrame:
    times = pd.date_range("2026-01-01T00:00:00Z", periods=rows, freq="15min")
    return pd.DataFrame(
        [
            {
                "time": timestamp,
                "open": 100.0 + index * 0.1,
                "high": 101.0 + index * 0.1,
                "low": 99.0 + index * 0.1,
                "close": 100.5 + index * 0.1,
                "volume": 1000.0 + index,
            }
            for index, timestamp in enumerate(times)
        ]
    )


def test_feature_library_shifts_decision_features_to_prevent_lookahead() -> None:
    candles = _candles()

    shifted = build_feature_frame(candles, shift_features=True)
    unshifted = build_feature_frame(candles, shift_features=False)

    assert pd.isna(shifted.loc[0, "return_1"])
    assert shifted.loc[30, "ema_50"] == unshifted.loc[29, "ema_50"]
    assert "spread_proxy_bps" in shifted.columns
    assert shifted.loc[0, "day_of_week"] == 3
    assert shifted.loc[0, "hour_of_day"] == 0


def test_professional_regime_detector_outputs_combined_regime_id() -> None:
    regimes = add_professional_regime_labels(_candles())

    latest = regimes.iloc[-1]

    assert latest["trend_state"] in {"STRONG_TREND", "WEAK_TREND", "RANGING"}
    assert latest["volatility_state"] in {"HIGH_VOL", "MEDIUM_VOL", "LOW_VOL"}
    assert latest["liquidity_state"] in {"HIGH_LIQ", "LOW_LIQ"}
    assert str(latest["regime_id"]).count("_") >= 4


def test_quant_research_repositories_persist_core_records() -> None:
    factory = create_session_factory("sqlite:///:memory:")
    init_db(factory)
    candles, quality = clean_ohlcv(_candles(20), timeframe="15m")
    feature_frame = build_feature_frame(candles)
    regime_frame = add_professional_regime_labels(candles)

    with session_scope(factory) as session:
        market_count = persist_market_data(
            MarketDataRepository(session),
            candles,
            symbol="BTCUSDT",
            timeframe="15m",
            source="test",
        )
        feature_count = persist_feature_frame(
            FeatureRepository(session),
            feature_frame,
            symbol="BTCUSDT",
            timeframe="15m",
        )
        regime_count = persist_regime_frame(
            RegimeRepository(session),
            regime_frame,
            symbol="BTCUSDT",
            timeframe="15m",
        )
        StrategyMetadataRepository(session).upsert(
            strategy_id="session_breakout_BTCUSDT_15m",
            name="session_breakout",
            family="breakout",
            parameters={"timeframe": "15m"},
        )
        BacktestResultRepository(session).create(
            run_id="run-1",
            strategy_id="session_breakout_BTCUSDT_15m",
            symbol="BTCUSDT",
            timeframe="15m",
            metrics={"profit_factor": 1.2},
            passed_validation=True,
        )
        ExecutionRepository(session).create(
            symbol="BTCUSDT",
            side="BUY",
            quantity=0.1,
            expected_price=100.0,
            actual_price=100.05,
            slippage_bps=5.0,
            status="filled",
        )
        PortfolioAllocationRepository(session).create(
            strategy_id="session_breakout_BTCUSDT_15m",
            allocated_capital=3000.0,
            weight=0.5,
        )
        PerformanceHealthRepository(session).create(
            strategy_id="session_breakout_BTCUSDT_15m",
            status="HEALTHY",
            expectancy=1.0,
        )
        SystemLogRepository(session).create(level="INFO", logger="test", event_type="research", message="ok")

    with session_scope(factory) as session:
        assert quality.missing_candles == 0
        assert market_count == 20
        assert feature_count == 20
        assert regime_count == 20
        assert len(session.scalars(select(MarketDataModel)).all()) == 20
        assert len(session.scalars(select(FeatureModel)).all()) == 20
        assert len(session.scalars(select(RegimeModel)).all()) == 20
        assert session.scalar(select(StrategyModel)) is not None
        assert session.scalar(select(BacktestResultModel)) is not None
        assert session.scalar(select(ExecutionModel)) is not None
        allocation = session.scalar(select(PortfolioAllocationModel))
        assert allocation is not None
        assert allocation.weight == 0.3
        assert session.scalar(select(PerformanceHealthModel)) is not None
        assert session.scalar(select(SystemLogModel)) is not None


def test_router_allocator_and_health_tracker_apply_safety_rules() -> None:
    router = SmartOrderRouter()
    passive = router.route(urgency=0.2, spread_proxy_bps=3.0, edge_bps=40.0)
    no_edge = router.route(urgency=1.0, spread_proxy_bps=20.0, edge_bps=-1.0)
    allocator = EqualWeightMetaAllocator(max_weight=0.3)
    allocations = allocator.allocate(
        capital=10_000,
        strategies=[
            StrategyHealthInput("healthy", "HEALTHY", expectancy=1.0, max_drawdown_pct=2.0),
            StrategyHealthInput("dead", "CRITICAL", expectancy=-1.0, max_drawdown_pct=5.0),
        ],
    )
    health = PerformanceHealthTracker(min_trades=10).classify(
        trade_count=20,
        expectancy=-0.1,
        profit_factor=0.9,
        max_drawdown_pct=5.0,
        slippage_bps=3.0,
        backtest_expectancy=1.0,
    )

    assert passive.order_type == "LIMIT"
    assert no_edge.order_type == "NONE"
    assert allocations[0].weight == 0.3
    assert allocations[1].active is False
    assert health.status == StrategyHealthStatus.CRITICAL
