"""Repository APIs for trading persistence models."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.persistence.models import (
    BacktestRunModel,
    BotSessionModel,
    ConfigModel,
    OrderLifecycleState,
    OrderModel,
    PositionModel,
    RiskEventModel,
    RiskStateModel,
    SignalModel,
    TradeModel,
    utc_now,
)
from trading_bot.analytics.metrics import PerformanceMetrics
from trading_bot.core.types import Signal, Trade
from trading_bot.execution.base import OrderResult, ProtectedOrderResult


class BotSessionRepository:
    """Persistence operations for bot sessions."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        mode: str,
        strategy_name: str,
        symbol: str,
        timeframe: str,
        config_snapshot: dict[str, object] | None = None,
    ) -> BotSessionModel:
        model = BotSessionModel(
            mode=mode,
            strategy_name=strategy_name,
            symbol=symbol,
            timeframe=timeframe,
            config_snapshot=config_snapshot or {},
        )
        self.session.add(model)
        self.session.flush()
        return model

    def list_recent(self, *, limit: int = 100) -> list[BotSessionModel]:
        statement = select(BotSessionModel).order_by(BotSessionModel.started_at.desc()).limit(limit)
        return list(self.session.scalars(statement))

    def finish(self, bot_session_id: int, *, status: str) -> BotSessionModel:
        model = self.session.get(BotSessionModel, bot_session_id)
        if model is None:
            raise ValueError(f"BotSession {bot_session_id} not found")
        model.status = status
        model.ended_at = utc_now()
        self.session.flush()
        return model


class SignalRepository:
    """Persistence operations for accepted strategy signals."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create_from_signal(
        self,
        signal: Signal,
        *,
        symbol: str,
        strategy_name: str,
        bot_session_id: int | None = None,
        status: str = "accepted",
        reason: str | None = None,
    ) -> SignalModel:
        model = SignalModel(
            bot_session_id=bot_session_id,
            symbol=symbol,
            strategy_name=strategy_name,
            side=signal.side.value,
            entry_price=signal.entry_price,
            stop_price=signal.stop_price,
            take_profit_price=signal.take_profit_price,
            quantity=signal.quantity,
            timestamp=signal.timestamp,
            status=status,
            reason=reason,
            payload=dict(signal.metadata),
        )
        self.session.add(model)
        self.session.flush()
        return model

    def list_recent(self, *, symbol: str | None = None, limit: int = 100) -> list[SignalModel]:
        statement = select(SignalModel)
        if symbol is not None:
            statement = statement.where(SignalModel.symbol == symbol)
        statement = statement.order_by(SignalModel.timestamp.desc()).limit(limit)
        return list(self.session.scalars(statement))


class OrderRepository:
    """Persistence operations for exchange orders and state transitions."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create_pending(
        self,
        *,
        symbol: str,
        side: str,
        quantity: float | None = None,
        signal_id: int | None = None,
        bot_session_id: int | None = None,
        order_type: str = "MARKET",
    ) -> OrderModel:
        model = OrderModel(
            bot_session_id=bot_session_id,
            signal_id=signal_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type=order_type,
        )
        self.session.add(model)
        self.session.flush()
        return model

    def apply_order_result(self, order_id: int, result: OrderResult) -> OrderModel:
        model = self._get(order_id)
        model.exchange_order_id = result.order_id
        model.avg_price = result.avg_price
        model.quantity = result.quantity if result.quantity is not None else model.quantity
        model.message = result.message
        model.state = OrderLifecycleState.ENTRY_PLACED if result.success else OrderLifecycleState.FAILED_UNPROTECTED
        if result.protected_order is not None:
            self._apply_protected_order_fields(model, result.protected_order, set_final_state=False)
        self.session.flush()
        return model

    def apply_protected_order_result(
        self,
        order_id: int,
        result: ProtectedOrderResult,
        *,
        emergency_close_order_id: str | None = None,
    ) -> OrderModel:
        model = self._get(order_id)
        self._apply_protected_order_fields(model, result, set_final_state=True)
        if emergency_close_order_id is not None:
            model.emergency_close_order_id = emergency_close_order_id
        self.session.flush()
        return model

    def set_state(self, order_id: int, state: OrderLifecycleState) -> OrderModel:
        model = self._get(order_id)
        model.state = state
        self.session.flush()
        return model

    def list_by_state(self, state: OrderLifecycleState) -> list[OrderModel]:
        statement = select(OrderModel).where(OrderModel.state == state).order_by(OrderModel.created_at.asc())
        return list(self.session.scalars(statement))

    def _get(self, order_id: int) -> OrderModel:
        model = self.session.get(OrderModel, order_id)
        if model is None:
            raise ValueError(f"Order {order_id} not found")
        return model

    def _apply_protected_order_fields(
        self,
        model: OrderModel,
        result: ProtectedOrderResult,
        *,
        set_final_state: bool,
    ) -> None:
        model.exchange_order_id = result.entry_order_id or model.exchange_order_id
        model.stop_order_id = result.stop_order_id
        model.take_profit_order_id = result.take_profit_order_id
        model.protected = result.protected
        model.requires_manual_review = result.requires_manual_review
        model.message = result.message
        if set_final_state:
            model.state = OrderLifecycleState.PROTECTED if result.protected else OrderLifecycleState.FAILED_UNPROTECTED


class TradeRepository:
    """Persistence operations for closed trades and backtest runs."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create_from_trade(
        self,
        trade: Trade,
        *,
        bot_session_id: int | None = None,
        signal_id: int | None = None,
        order_id: int | None = None,
        source: str = "live",
    ) -> TradeModel:
        model = TradeModel(
            bot_session_id=bot_session_id,
            signal_id=signal_id,
            order_id=order_id,
            symbol=trade.symbol,
            side=trade.side.value,
            quantity=trade.quantity,
            entry_price=trade.entry_price,
            exit_price=trade.exit_price,
            pnl=trade.pnl,
            pnl_pct=trade.pnl_pct,
            entry_time=trade.entry_time,
            exit_time=trade.exit_time,
            exit_reason=trade.exit_reason,
            fees=trade.fees,
            slippage_usd=trade.slippage_usd,
            source=source,
        )
        self.session.add(model)
        self.session.flush()
        return model

    def create_backtest_run(
        self,
        *,
        strategy_name: str,
        symbol: str,
        timeframe: str,
        initial_capital: float,
        final_capital: float,
        metrics: PerformanceMetrics,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        config_snapshot: dict[str, object] | None = None,
    ) -> BacktestRunModel:
        model = BacktestRunModel(
            strategy_name=strategy_name,
            symbol=symbol,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            final_capital=final_capital,
            total_trades=metrics.total_trades,
            total_return_pct=metrics.total_return_pct,
            sharpe_ratio=metrics.sharpe_ratio,
            sortino_ratio=metrics.sortino_ratio,
            max_drawdown_pct=metrics.max_drawdown_pct,
            win_rate=metrics.win_rate,
            profit_factor=metrics.profit_factor,
            expectancy=metrics.expectancy,
            config_snapshot=config_snapshot or {},
        )
        self.session.add(model)
        self.session.flush()
        return model

    def get(self, trade_id: int) -> TradeModel | None:
        return self.session.get(TradeModel, trade_id)

    def list_recent(self, *, symbol: str | None = None, limit: int = 100) -> list[TradeModel]:
        statement = select(TradeModel)
        if symbol is not None:
            statement = statement.where(TradeModel.symbol == symbol)
        statement = statement.order_by(TradeModel.exit_time.desc()).limit(limit)
        return list(self.session.scalars(statement))

    def list_backtest_runs(self, *, limit: int = 100) -> list[BacktestRunModel]:
        statement = select(BacktestRunModel).order_by(BacktestRunModel.created_at.desc()).limit(limit)
        return list(self.session.scalars(statement))


class RiskEventRepository:
    """Persistence operations for risk rejections and incidents."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        symbol: str,
        event_type: str,
        severity: str = "info",
        reason: str = "",
        bot_session_id: int | None = None,
        payload: dict[str, Any] | None = None,
    ) -> RiskEventModel:
        model = RiskEventModel(
            bot_session_id=bot_session_id,
            symbol=symbol,
            event_type=event_type,
            severity=severity,
            reason=reason,
            payload=payload or {},
        )
        self.session.add(model)
        self.session.flush()
        return model

    def list_recent(self, *, symbol: str | None = None, limit: int = 100) -> list[RiskEventModel]:
        statement = select(RiskEventModel)
        if symbol is not None:
            statement = statement.where(RiskEventModel.symbol == symbol)
        statement = statement.order_by(RiskEventModel.created_at.desc()).limit(limit)
        return list(self.session.scalars(statement))


class PositionRepository:
    """Persistence operations for position snapshots."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def list_recent(self, *, symbol: str | None = None, limit: int = 100) -> list[PositionModel]:
        statement = select(PositionModel)
        if symbol is not None:
            statement = statement.where(PositionModel.symbol == symbol)
        statement = statement.order_by(PositionModel.opened_at.desc()).limit(limit)
        return list(self.session.scalars(statement))


class ConfigRepository:
    """Persistence operations for API-managed config snapshots."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def list_all(self) -> list[ConfigModel]:
        statement = select(ConfigModel).order_by(ConfigModel.created_at.desc())
        return list(self.session.scalars(statement))

    def upsert(self, *, name: str, payload: dict[str, object], is_active: bool = False) -> ConfigModel:
        model = self.session.scalar(select(ConfigModel).where(ConfigModel.name == name))
        if model is None:
            model = ConfigModel(name=name, payload=payload, is_active=is_active)
            self.session.add(model)
        else:
            model.payload = payload
            model.is_active = is_active
            model.updated_at = utc_now()
        if is_active:
            for other in self.session.scalars(select(ConfigModel).where(ConfigModel.name != name)):
                other.is_active = False
        self.session.flush()
        return model


class RiskStateRepository:
    """Persistence operations for operator risk controls."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_or_create(self) -> RiskStateModel:
        model = self.session.scalar(select(RiskStateModel).order_by(RiskStateModel.id.asc()))
        if model is None:
            model = RiskStateModel()
            self.session.add(model)
            self.session.flush()
        return model

    def set_kill_switch(self, *, enabled: bool, reason: str = "") -> RiskStateModel:
        model = self.get_or_create()
        model.kill_switch_enabled = enabled
        model.reason = reason
        model.updated_at = utc_now()
        self.session.flush()
        return model

    def update_state(
        self,
        *,
        kill_switch_enabled: bool | None = None,
        manual_pause_enabled: bool | None = None,
        daily_loss_locked: bool | None = None,
        drawdown_locked: bool | None = None,
        reason: str | None = None,
    ) -> RiskStateModel:
        model = self.get_or_create()
        if kill_switch_enabled is not None:
            model.kill_switch_enabled = kill_switch_enabled
        if manual_pause_enabled is not None:
            model.manual_pause_enabled = manual_pause_enabled
        if daily_loss_locked is not None:
            model.daily_loss_locked = daily_loss_locked
        if drawdown_locked is not None:
            model.drawdown_locked = drawdown_locked
        if reason is not None:
            model.reason = reason
        model.updated_at = utc_now()
        self.session.flush()
        return model
