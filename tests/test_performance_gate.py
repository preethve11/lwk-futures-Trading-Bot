from __future__ import annotations

from app.core.config import Settings
from app.ops.performance_gate import evaluate_strategy_performance_gate
from app.persistence.database import SessionFactory, create_session_factory, init_db, session_scope
from app.persistence.repositories import TradeRepository
from trading_bot.analytics.metrics import PerformanceMetrics


def _session_factory() -> SessionFactory:
    factory = create_session_factory("sqlite:///:memory:")
    init_db(factory)
    return factory


def _metrics(
    *,
    total_trades: int = 30,
    profit_factor: float = 1.5,
    expectancy: float = 2.0,
    sharpe: float = 0.8,
    drawdown: float = -8.0,
) -> PerformanceMetrics:
    return PerformanceMetrics(
        total_return_pct=12.0,
        sharpe_ratio=sharpe,
        sortino_ratio=1.0,
        max_drawdown_pct=drawdown,
        win_rate=0.55,
        profit_factor=profit_factor,
        expectancy=expectancy,
        total_trades=total_trades,
        winning_trades=max(1, total_trades // 2),
        losing_trades=max(0, total_trades - max(1, total_trades // 2)),
        avg_win=5.0,
        avg_loss=-3.0,
    )


def test_performance_gate_fails_when_no_backtest_exists() -> None:
    factory = _session_factory()

    with session_scope(factory) as session:
        result = evaluate_strategy_performance_gate(session, Settings())

    assert result.allowed is False
    assert result.violations[0].field == "backtest_run"


def test_performance_gate_allows_recent_profitable_backtest() -> None:
    factory = _session_factory()
    settings = Settings(live_gate_min_trades=20, live_gate_min_profit_factor=1.1, live_gate_max_drawdown_pct=20)
    with session_scope(factory) as session:
        TradeRepository(session).create_backtest_run(
            strategy_name=settings.strategy_name,
            symbol=settings.symbol,
            timeframe=settings.timeframe,
            initial_capital=10_000,
            final_capital=10_500,
            metrics=_metrics(),
        )
        result = evaluate_strategy_performance_gate(session, settings)

    assert result.allowed is True
    assert result.violations == []
    assert result.metrics["profit_factor"] == 1.5


def test_performance_gate_blocks_weak_backtest_metrics() -> None:
    factory = _session_factory()
    settings = Settings(live_gate_min_trades=20, live_gate_min_profit_factor=1.1, live_gate_max_drawdown_pct=20)
    with session_scope(factory) as session:
        TradeRepository(session).create_backtest_run(
            strategy_name=settings.strategy_name,
            symbol=settings.symbol,
            timeframe=settings.timeframe,
            initial_capital=10_000,
            final_capital=9_500,
            metrics=_metrics(total_trades=5, profit_factor=0.8, expectancy=-1.0, sharpe=-0.4, drawdown=-25.0),
        )
        result = evaluate_strategy_performance_gate(session, settings)

    fields = {violation.field for violation in result.violations}

    assert result.allowed is False
    assert {"total_trades", "profit_factor", "expectancy", "sharpe_ratio", "max_drawdown_pct"}.issubset(fields)
