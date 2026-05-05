from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from app.core.config import Settings
from app.persistence.database import SessionFactory, create_session_factory, init_db, session_scope
from app.persistence.models import BacktestRunModel, OrderLifecycleState, OrderModel, SignalModel, TradeModel
from app.persistence.repositories import BotSessionRepository, OrderRepository, SignalRepository, TradeRepository
from app.persistence.state_machine import OrderStateMachine
from app.workers.live_trader import LiveTrader
from trading_bot.analytics.metrics import PerformanceMetrics
from trading_bot.core.types import Signal, SignalSide, Trade
from trading_bot.execution.base import OrderResult


def _session_factory() -> SessionFactory:
    factory = create_session_factory("sqlite:///:memory:")
    init_db(factory)
    return factory


def _signal() -> Signal:
    return Signal(
        side=SignalSide.LONG,
        entry_price=100.0,
        stop_price=99.0,
        take_profit_price=102.0,
        quantity=0.5,
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        metadata={"reason": "test"},
    )


def _trade() -> Trade:
    return Trade(
        symbol="ZECUSDT",
        side=SignalSide.LONG,
        quantity=0.5,
        entry_price=100.0,
        exit_price=102.0,
        pnl=0.96,
        pnl_pct=1.92,
        entry_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        exit_time=datetime(2026, 1, 1, 1, tzinfo=timezone.utc),
        exit_reason="take_profit",
        fees=0.04,
    )


def _metrics() -> PerformanceMetrics:
    return PerformanceMetrics(
        total_return_pct=1.0,
        sharpe_ratio=1.2,
        sortino_ratio=1.3,
        max_drawdown_pct=-0.5,
        win_rate=1.0,
        profit_factor=2.0,
        expectancy=0.96,
        total_trades=1,
        winning_trades=1,
        losing_trades=0,
        avg_win=0.96,
        avg_loss=0.0,
    )


def test_repositories_persist_signal_order_trade_and_backtest_run() -> None:
    factory = _session_factory()

    with session_scope(factory) as session:
        bot_session = BotSessionRepository(session).create(
            mode="backtest",
            strategy_name="ema_rsi_vwap",
            symbol="ZECUSDT",
            timeframe="5m",
            config_snapshot={"leverage": 5},
        )
        signal = SignalRepository(session).create_from_signal(
            _signal(),
            symbol="ZECUSDT",
            strategy_name="ema_rsi_vwap",
            bot_session_id=bot_session.id,
        )
        order = OrderRepository(session).create_pending(
            symbol="ZECUSDT",
            side=SignalSide.LONG.value,
            quantity=0.5,
            signal_id=signal.id,
            bot_session_id=bot_session.id,
        )
        TradeRepository(session).create_from_trade(
            _trade(),
            bot_session_id=bot_session.id,
            signal_id=signal.id,
            order_id=order.id,
            source="backtest",
        )
        TradeRepository(session).create_backtest_run(
            strategy_name="ema_rsi_vwap",
            symbol="ZECUSDT",
            timeframe="5m",
            initial_capital=10_000.0,
            final_capital=10_001.0,
            metrics=_metrics(),
        )

    with session_scope(factory) as session:
        assert len(session.scalars(select(SignalModel)).all()) == 1
        assert len(session.scalars(select(OrderModel)).all()) == 1
        assert len(session.scalars(select(TradeModel)).all()) == 1
        assert len(session.scalars(select(BacktestRunModel)).all()) == 1


def test_order_state_machine_requires_entry_before_protection() -> None:
    state_machine = OrderStateMachine()

    try:
        state_machine.mark_tp_placed()
    except ValueError as exc:
        assert "entry must be placed" in str(exc)
    else:
        raise AssertionError("take-profit protection should require an entry order")

    assert state_machine.mark_entry_placed() == OrderLifecycleState.ENTRY_PLACED
    assert state_machine.mark_tp_placed() == OrderLifecycleState.TP_PLACED
    assert state_machine.mark_sl_placed() == OrderLifecycleState.PROTECTED


def test_live_trader_persists_signal_and_protected_order_result() -> None:
    factory = _session_factory()
    settings = Settings(database_url="sqlite:///:memory:")
    trader = LiveTrader(settings, session_factory=factory)

    bot_session_id = trader._start_bot_session(factory)
    signal_id, order_id = trader._record_live_signal(factory, bot_session_id, _signal())
    trader._record_order_result(
        factory,
        order_id,
        OrderResult(success=True, order_id="123", avg_price=100.1, quantity=0.5),
    )

    assert signal_id is not None
    with session_scope(factory) as session:
        order = session.get(OrderModel, order_id)
        assert order is not None
        assert order.state == OrderLifecycleState.PROTECTED
        assert order.exchange_order_id == "123"
