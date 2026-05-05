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
    quantity: Mapped[float | None] = mapped_column(nullable=True)
    avg_price: Mapped[float | None] = mapped_column(nullable=True)
    limit_price: Mapped[float | None] = mapped_column(nullable=True)
    stop_price: Mapped[float | None] = mapped_column(nullable=True)
    reduce_only: Mapped[bool] = mapped_column(default=False)
    message: Mapped[str] = mapped_column(String(500), default="")
    raw_response: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
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
    __table_args__ = (Index("ix_trades_symbol_exit_time", "symbol", "exit_time"),)

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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    bot_session: Mapped[BotSessionModel | None] = relationship(back_populates="trades")
    signal: Mapped[SignalModel | None] = relationship(back_populates="trades")
    order: Mapped[OrderModel | None] = relationship(back_populates="trades")


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
