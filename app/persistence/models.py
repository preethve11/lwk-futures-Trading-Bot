"""SQLAlchemy models for trading runtime and analytics persistence."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp for database defaults."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Base class for persistence models."""


class OrderLifecycleState(str, Enum):
    """Order protection lifecycle states for bracketed futures entries."""

    PENDING = "PENDING"
    ENTRY_PLACED = "ENTRY_PLACED"
    TP_PLACED = "TP_PLACED"
    SL_PLACED = "SL_PLACED"
    PROTECTED = "PROTECTED"
    FAILED_UNPROTECTED = "FAILED_UNPROTECTED"


class BotSessionModel(Base):
    """A live or backtest bot process session."""

    __tablename__ = "bot_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()), index=True)
    mode: Mapped[str] = mapped_column(String(20))
    strategy_name: Mapped[str] = mapped_column(String(120))
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    timeframe: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(32), default="running", index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    config_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)

    signals: Mapped[list[SignalModel]] = relationship(back_populates="bot_session")
    orders: Mapped[list[OrderModel]] = relationship(back_populates="bot_session")
    trades: Mapped[list[TradeModel]] = relationship(back_populates="bot_session")
    positions: Mapped[list[PositionModel]] = relationship(back_populates="bot_session")
    risk_events: Mapped[list[RiskEventModel]] = relationship(back_populates="bot_session")
    ai_reports: Mapped[list[AIReportModel]] = relationship(back_populates="bot_session")
    exchange_fills: Mapped[list[ExchangeFillModel]] = relationship(back_populates="bot_session")
    account_snapshots: Mapped[list[AccountSnapshotModel]] = relationship(back_populates="bot_session")


class ConfigModel(Base):
    """Versioned API-managed configuration snapshot."""

    __tablename__ = "configs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class RiskStateModel(Base):
    """Persisted operator risk controls."""

    __tablename__ = "risk_state"

    id: Mapped[int] = mapped_column(primary_key=True)
    kill_switch_enabled: Mapped[bool] = mapped_column(default=False, index=True)
    manual_pause_enabled: Mapped[bool] = mapped_column(default=False, index=True)
    daily_loss_locked: Mapped[bool] = mapped_column(default=False, index=True)
    drawdown_locked: Mapped[bool] = mapped_column(default=False, index=True)
    reason: Mapped[str] = mapped_column(String(500), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class SignalModel(Base):
    """A strategy signal accepted for execution consideration."""

    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(primary_key=True)
    bot_session_id: Mapped[int | None] = mapped_column(ForeignKey("bot_sessions.id"), nullable=True, index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    strategy_name: Mapped[str] = mapped_column(String(120))
    side: Mapped[str] = mapped_column(String(12), index=True)
    entry_price: Mapped[float]
    stop_price: Mapped[float]
    take_profit_price: Mapped[float]
    quantity: Mapped[float]
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(32), default="accepted", index=True)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    bot_session: Mapped[BotSessionModel | None] = relationship(back_populates="signals")
    orders: Mapped[list[OrderModel]] = relationship(back_populates="signal")
    trades: Mapped[list[TradeModel]] = relationship(back_populates="signal")
    ai_reports: Mapped[list[AIReportModel]] = relationship(back_populates="signal")


class OrderModel(Base):
    """Exchange order attempt and lifecycle state."""

    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("exchange_order_id", name="uq_orders_exchange_order_id"),
        Index("ix_orders_symbol_state", "symbol", "state"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    bot_session_id: Mapped[int | None] = mapped_column(ForeignKey("bot_sessions.id"), nullable=True, index=True)
    signal_id: Mapped[int | None] = mapped_column(ForeignKey("signals.id"), nullable=True, index=True)
    exchange_order_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    side: Mapped[str] = mapped_column(String(12), index=True)
    order_type: Mapped[str] = mapped_column(String(32), default="MARKET")
    state: Mapped[OrderLifecycleState] = mapped_column(default=OrderLifecycleState.PENDING, index=True)
    exchange_status: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    quantity: Mapped[float | None] = mapped_column(nullable=True)
    filled_quantity: Mapped[float | None] = mapped_column(nullable=True)
    remaining_quantity: Mapped[float | None] = mapped_column(nullable=True)
    avg_price: Mapped[float | None] = mapped_column(nullable=True)
    stop_order_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    take_profit_order_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    protected: Mapped[bool] = mapped_column(default=False, index=True)
    requires_manual_review: Mapped[bool] = mapped_column(default=False, index=True)
    emergency_close_order_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    limit_price: Mapped[float | None] = mapped_column(nullable=True)
    stop_price: Mapped[float | None] = mapped_column(nullable=True)
    reduce_only: Mapped[bool] = mapped_column(default=False)
    message: Mapped[str] = mapped_column(String(500), default="")
    raw_response: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    last_reconciled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    bot_session: Mapped[BotSessionModel | None] = relationship(back_populates="orders")
    signal: Mapped[SignalModel | None] = relationship(back_populates="orders")
    trades: Mapped[list[TradeModel]] = relationship(back_populates="order")


class PositionModel(Base):
    """Persisted position snapshot."""

    __tablename__ = "positions"
    __table_args__ = (Index("ix_positions_symbol_status", "symbol", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    bot_session_id: Mapped[int | None] = mapped_column(ForeignKey("bot_sessions.id"), nullable=True, index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    side: Mapped[str] = mapped_column(String(12))
    quantity: Mapped[float]
    entry_price: Mapped[float]
    unrealized_pnl: Mapped[float] = mapped_column(default=0.0)
    leverage: Mapped[int] = mapped_column(default=1)
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    bot_session: Mapped[BotSessionModel | None] = relationship(back_populates="positions")


class TradeModel(Base):
    """Closed trade event for live trading or backtests."""

    __tablename__ = "trades"
    __table_args__ = (
        UniqueConstraint("exchange_trade_id", name="uq_trades_exchange_trade_id"),
        Index("ix_trades_symbol_exit_time", "symbol", "exit_time"),
        Index("ix_trades_exchange_order_id", "exchange_order_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    bot_session_id: Mapped[int | None] = mapped_column(ForeignKey("bot_sessions.id"), nullable=True, index=True)
    signal_id: Mapped[int | None] = mapped_column(ForeignKey("signals.id"), nullable=True, index=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), nullable=True, index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    side: Mapped[str] = mapped_column(String(12))
    quantity: Mapped[float]
    entry_price: Mapped[float]
    exit_price: Mapped[float]
    pnl: Mapped[float]
    pnl_pct: Mapped[float]
    entry_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    exit_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    exit_reason: Mapped[str] = mapped_column(String(64))
    fees: Mapped[float] = mapped_column(default=0.0)
    slippage_usd: Mapped[float] = mapped_column(default=0.0)
    source: Mapped[str] = mapped_column(String(32), default="live", index=True)
    exchange_trade_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    exchange_order_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    bot_session: Mapped[BotSessionModel | None] = relationship(back_populates="trades")
    signal: Mapped[SignalModel | None] = relationship(back_populates="trades")
    order: Mapped[OrderModel | None] = relationship(back_populates="trades")
    ai_reports: Mapped[list[AIReportModel]] = relationship(back_populates="trade")
    exchange_fills: Mapped[list[ExchangeFillModel]] = relationship(back_populates="trade")


class ExchangeFillModel(Base):
    """Raw exchange fill ledger for idempotent Binance account-trade reconciliation."""

    __tablename__ = "exchange_fills"
    __table_args__ = (
        UniqueConstraint("exchange_trade_id", name="uq_exchange_fills_exchange_trade_id"),
        Index("ix_exchange_fills_symbol_event_time", "symbol", "event_time"),
        Index("ix_exchange_fills_exchange_order_id", "exchange_order_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    bot_session_id: Mapped[int | None] = mapped_column(ForeignKey("bot_sessions.id"), nullable=True, index=True)
    trade_id: Mapped[int | None] = mapped_column(ForeignKey("trades.id"), nullable=True, index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    exchange_trade_id: Mapped[str] = mapped_column(String(120))
    exchange_order_id: Mapped[str] = mapped_column(String(120), default="")
    side: Mapped[str] = mapped_column(String(12), index=True)
    position_side: Mapped[str] = mapped_column(String(16), default="")
    price: Mapped[float]
    quantity: Mapped[float]
    quote_quantity: Mapped[float] = mapped_column(default=0.0)
    realized_pnl: Mapped[float] = mapped_column(default=0.0)
    commission: Mapped[float] = mapped_column(default=0.0)
    commission_asset: Mapped[str] = mapped_column(String(24), default="")
    buyer: Mapped[bool] = mapped_column(default=False)
    maker: Mapped[bool] = mapped_column(default=False)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    raw_payload: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)

    bot_session: Mapped[BotSessionModel | None] = relationship(back_populates="exchange_fills")
    trade: Mapped[TradeModel | None] = relationship(back_populates="exchange_fills")


class AccountSnapshotModel(Base):
    """Live futures wallet/equity snapshot from the exchange account state."""

    __tablename__ = "account_snapshots"
    __table_args__ = (Index("ix_account_snapshots_asset_event_time", "asset", "event_time"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    bot_session_id: Mapped[int | None] = mapped_column(ForeignKey("bot_sessions.id"), nullable=True, index=True)
    asset: Mapped[str] = mapped_column(String(24), index=True)
    wallet_balance: Mapped[float]
    unrealized_pnl: Mapped[float] = mapped_column(default=0.0)
    margin_balance: Mapped[float]
    available_balance: Mapped[float]
    max_withdraw_amount: Mapped[float | None] = mapped_column(nullable=True)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    raw_response: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)

    bot_session: Mapped[BotSessionModel | None] = relationship(back_populates="account_snapshots")


class RiskEventModel(Base):
    """Risk manager rejection, limit, or incident event."""

    __tablename__ = "risk_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    bot_session_id: Mapped[int | None] = mapped_column(ForeignKey("bot_sessions.id"), nullable=True, index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    severity: Mapped[str] = mapped_column(String(32), default="info", index=True)
    reason: Mapped[str] = mapped_column(String(500), default="")
    payload: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)

    bot_session: Mapped[BotSessionModel | None] = relationship(back_populates="risk_events")


class BacktestRunModel(Base):
    """Aggregate backtest run persisted for analytics and auditability."""

    __tablename__ = "backtest_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()), index=True)
    strategy_name: Mapped[str] = mapped_column(String(120), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    timeframe: Mapped[str] = mapped_column(String(16))
    start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    initial_capital: Mapped[float]
    final_capital: Mapped[float]
    total_trades: Mapped[int]
    total_return_pct: Mapped[float]
    sharpe_ratio: Mapped[float]
    sortino_ratio: Mapped[float]
    max_drawdown_pct: Mapped[float]
    win_rate: Mapped[float]
    profit_factor: Mapped[float]
    expectancy: Mapped[float]
    config_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class MarketDataModel(Base):
    """Normalized OHLCV candle persisted for research and replay."""

    __tablename__ = "market_data"
    __table_args__ = (
        UniqueConstraint("symbol", "timeframe", "open_time", name="uq_market_data_symbol_timeframe_open_time"),
        Index("ix_market_data_symbol_timeframe_open_time", "symbol", "timeframe", "open_time"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    timeframe: Mapped[str] = mapped_column(String(16), index=True)
    open_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    close_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    open: Mapped[float]
    high: Mapped[float]
    low: Mapped[float]
    close: Mapped[float]
    volume: Mapped[float]
    quote_volume: Mapped[float] = mapped_column(default=0.0)
    trades_count: Mapped[int | None] = mapped_column(nullable=True)
    source: Mapped[str] = mapped_column(String(64), default="unknown", index=True)
    is_closed: Mapped[bool] = mapped_column(default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class FeatureModel(Base):
    """Feature snapshot for one candle, keyed by symbol/timeframe/time/version."""

    __tablename__ = "features"
    __table_args__ = (
        UniqueConstraint(
            "symbol",
            "timeframe",
            "event_time",
            "feature_set_version",
            name="uq_features_symbol_timeframe_event_time_version",
        ),
        Index("ix_features_symbol_timeframe_event_time", "symbol", "timeframe", "event_time"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    timeframe: Mapped[str] = mapped_column(String(16), index=True)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    feature_set_version: Mapped[str] = mapped_column(String(64), default="v1", index=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class RegimeModel(Base):
    """Market regime label attached to one candle."""

    __tablename__ = "regimes"
    __table_args__ = (
        UniqueConstraint(
            "symbol",
            "timeframe",
            "event_time",
            "detector_version",
            name="uq_regimes_symbol_timeframe_event_time_version",
        ),
        Index("ix_regimes_symbol_timeframe_event_time", "symbol", "timeframe", "event_time"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    timeframe: Mapped[str] = mapped_column(String(16), index=True)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    detector_version: Mapped[str] = mapped_column(String(64), default="v1", index=True)
    trend_state: Mapped[str] = mapped_column(String(32), index=True)
    volatility_state: Mapped[str] = mapped_column(String(32), index=True)
    liquidity_state: Mapped[str] = mapped_column(String(32), index=True)
    regime_id: Mapped[str] = mapped_column(String(120), index=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class StrategyModel(Base):
    """Registered strategy candidate and parameter snapshot."""

    __tablename__ = "strategies"

    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_id: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    family: Mapped[str] = mapped_column(String(80), default="", index=True)
    version: Mapped[str] = mapped_column(String(64), default="v1")
    status: Mapped[str] = mapped_column(String(32), default="candidate", index=True)
    parameters: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    allowed_regimes: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class BacktestResultModel(Base):
    """Detailed validation result for a strategy candidate."""

    __tablename__ = "backtest_results"
    __table_args__ = (Index("ix_backtest_results_strategy_symbol_timeframe", "strategy_id", "symbol", "timeframe"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    strategy_id: Mapped[str] = mapped_column(String(160), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    timeframe: Mapped[str] = mapped_column(String(16), index=True)
    start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metrics: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    regime_metrics: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    fee_bps: Mapped[float] = mapped_column(default=0.0)
    slippage_bps: Mapped[float] = mapped_column(default=0.0)
    passed_validation: Mapped[bool] = mapped_column(default=False, index=True)
    rejection_reason: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class ExecutionModel(Base):
    """Expected-vs-actual execution quality record."""

    __tablename__ = "executions"
    __table_args__ = (
        UniqueConstraint("exchange_execution_id", name="uq_executions_exchange_execution_id"),
        Index("ix_executions_symbol_event_time", "symbol", "event_time"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), nullable=True, index=True)
    exchange_execution_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    strategy_id: Mapped[str] = mapped_column(String(160), default="", index=True)
    mode: Mapped[str] = mapped_column(String(24), default="paper", index=True)
    side: Mapped[str] = mapped_column(String(12), index=True)
    order_type: Mapped[str] = mapped_column(String(32), default="MARKET")
    expected_price: Mapped[float | None] = mapped_column(nullable=True)
    actual_price: Mapped[float | None] = mapped_column(nullable=True)
    quantity: Mapped[float]
    fee: Mapped[float] = mapped_column(default=0.0)
    fee_asset: Mapped[str] = mapped_column(String(24), default="")
    slippage_bps: Mapped[float | None] = mapped_column(nullable=True)
    latency_ms: Mapped[float | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="submitted", index=True)
    raw_payload: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class PortfolioAllocationModel(Base):
    """Capital allocation decision for a strategy candidate."""

    __tablename__ = "portfolio_allocations"
    __table_args__ = (Index("ix_portfolio_allocations_strategy_created_at", "strategy_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_id: Mapped[str] = mapped_column(String(160), index=True)
    symbol: Mapped[str] = mapped_column(String(32), default="", index=True)
    allocated_capital: Mapped[float]
    weight: Mapped[float]
    max_weight: Mapped[float] = mapped_column(default=0.30)
    regime_id: Mapped[str] = mapped_column(String(120), default="", index=True)
    reason: Mapped[str] = mapped_column(String(500), default="")
    active: Mapped[bool] = mapped_column(default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class PerformanceHealthModel(Base):
    """Live/paper strategy health snapshot for kill/reduce decisions."""

    __tablename__ = "performance_health"
    __table_args__ = (Index("ix_performance_health_strategy_checked_at", "strategy_id", "checked_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_id: Mapped[str] = mapped_column(String(160), index=True)
    symbol: Mapped[str] = mapped_column(String(32), default="", index=True)
    timeframe: Mapped[str] = mapped_column(String(16), default="", index=True)
    status: Mapped[str] = mapped_column(String(32), default="HEALTHY", index=True)
    expectancy: Mapped[float] = mapped_column(default=0.0)
    profit_factor: Mapped[float] = mapped_column(default=0.0)
    sharpe_ratio: Mapped[float] = mapped_column(default=0.0)
    max_drawdown_pct: Mapped[float] = mapped_column(default=0.0)
    win_rate: Mapped[float] = mapped_column(default=0.0)
    trade_count: Mapped[int] = mapped_column(default=0)
    slippage_bps: Mapped[float] = mapped_column(default=0.0)
    degradation_pct: Mapped[float] = mapped_column(default=0.0)
    reason: Mapped[str] = mapped_column(String(500), default="")
    payload: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class SystemLogModel(Base):
    """Structured operational log persisted for dashboard/audit use."""

    __tablename__ = "system_logs"
    __table_args__ = (Index("ix_system_logs_level_created_at", "level", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    level: Mapped[str] = mapped_column(String(24), index=True)
    logger: Mapped[str] = mapped_column(String(160), default="", index=True)
    event_type: Mapped[str] = mapped_column(String(80), default="", index=True)
    message: Mapped[str] = mapped_column(String(1000), default="")
    payload: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class AIReportModel(Base):
    """Advisory-only AI journal report for signal and trade decisions."""

    __tablename__ = "ai_reports"
    __table_args__ = (Index("ix_ai_reports_symbol_created_at", "symbol", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    bot_session_id: Mapped[int | None] = mapped_column(ForeignKey("bot_sessions.id"), nullable=True, index=True)
    signal_id: Mapped[int | None] = mapped_column(ForeignKey("signals.id"), nullable=True, index=True)
    trade_id: Mapped[int | None] = mapped_column(ForeignKey("trades.id"), nullable=True, index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    strategy_name: Mapped[str] = mapped_column(String(120))
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    model: Mapped[str] = mapped_column(String(120))
    prompt: Mapped[str] = mapped_column(String(4000), default="")
    report_text: Mapped[str] = mapped_column(String(4000), default="")
    input_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    risk_state: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    market_regime: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    outcome: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    raw_response: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)

    bot_session: Mapped[BotSessionModel | None] = relationship(back_populates="ai_reports")
    signal: Mapped[SignalModel | None] = relationship(back_populates="ai_reports")
    trade: Mapped[TradeModel | None] = relationship(back_populates="ai_reports")
