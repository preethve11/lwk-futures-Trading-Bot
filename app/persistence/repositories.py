"""Repository APIs for trading persistence models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.persistence.models import (
    AIReportModel,
    AccountSnapshotModel,
    BacktestRunModel,
    BotSessionModel,
    ConfigModel,
    ExchangeFillModel,
    OrderLifecycleState,
    OrderModel,
    PositionModel,
    RiskEventModel,
    RiskStateModel,
    SignalModel,
    TradeModel,
    utc_now,
)
from app.exchange.fills import ExchangeFill
from trading_bot.analytics.metrics import PerformanceMetrics
from trading_bot.core.types import Position, Signal, Trade
from trading_bot.execution.base import AccountSnapshot, ExchangeOrderStatus, OrderResult, ProtectedOrderResult


@dataclass(frozen=True)
class ExchangeFillAggregate:
    """Fill aggregate for one exchange order."""

    exchange_order_id: str
    fill_count: int = 0
    quantity: float = 0.0
    quote_quantity: float = 0.0
    realized_pnl: float = 0.0
    commission: float = 0.0

    @property
    def avg_price(self) -> float | None:
        if self.quantity <= 0:
            return None
        return self.quote_quantity / self.quantity


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
        model.filled_quantity = result.quantity if result.success and result.quantity is not None else model.filled_quantity
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

    def list_unprotected_for_recovery(self, *, limit: int = 100) -> list[OrderModel]:
        statement = (
            select(OrderModel)
            .where(
                (OrderModel.state == OrderLifecycleState.FAILED_UNPROTECTED)
                | (OrderModel.requires_manual_review.is_(True))
            )
            .where(OrderModel.protected.is_(False))
            .where(OrderModel.emergency_close_order_id.is_(None))
            .order_by(OrderModel.created_at.asc())
            .limit(limit)
        )
        return list(self.session.scalars(statement))

    def list_exchange_reconcilable(self, *, limit: int = 100) -> list[OrderModel]:
        statement = (
            select(OrderModel)
            .where(OrderModel.exchange_order_id.is_not(None))
            .where(OrderModel.state != OrderLifecycleState.FAILED_UNPROTECTED)
            .order_by(OrderModel.updated_at.asc())
            .limit(limit)
        )
        return list(self.session.scalars(statement))

    def apply_exchange_order_status(
        self,
        order_id: int,
        status: ExchangeOrderStatus,
        *,
        fill_aggregate: ExchangeFillAggregate | None = None,
    ) -> OrderModel:
        model = self._get(order_id)
        model.exchange_status = status.status or model.exchange_status
        original_quantity = status.original_quantity if status.original_quantity is not None else model.quantity
        status_filled = status.executed_quantity if status.executed_quantity is not None else None
        aggregate_filled = fill_aggregate.quantity if fill_aggregate is not None and fill_aggregate.quantity > 0 else None
        filled_values = [value for value in [status_filled, aggregate_filled, model.filled_quantity] if value is not None]
        filled_quantity = max(filled_values) if filled_values else 0.0
        model.quantity = original_quantity
        model.filled_quantity = filled_quantity
        model.remaining_quantity = max(0.0, (original_quantity or 0.0) - filled_quantity)
        model.avg_price = self._coalesce_avg_price(status, fill_aggregate, model.avg_price)
        model.last_reconciled_at = utc_now()
        raw_response = dict(model.raw_response or {})
        raw_response["exchange_lifecycle"] = {
            "order_status": status.raw_response,
            "fill_aggregate": self._fill_aggregate_payload(fill_aggregate),
        }
        model.raw_response = raw_response
        if status.status in {"FILLED", "PARTIALLY_FILLED"} and model.state == OrderLifecycleState.PENDING:
            model.state = OrderLifecycleState.ENTRY_PLACED
        if status.status in {"REJECTED", "EXPIRED"}:
            model.state = OrderLifecycleState.FAILED_UNPROTECTED
            model.requires_manual_review = True
            model.message = f"exchange order status is {status.status}"
        if status.status == "CANCELED" and filled_quantity <= 0:
            model.state = OrderLifecycleState.FAILED_UNPROTECTED
            model.requires_manual_review = True
            model.message = "exchange order was canceled before fill"
        self.session.flush()
        return model

    def _coalesce_avg_price(
        self,
        status: ExchangeOrderStatus,
        fill_aggregate: ExchangeFillAggregate | None,
        current_avg_price: float | None,
    ) -> float | None:
        if fill_aggregate is not None and fill_aggregate.avg_price is not None:
            return fill_aggregate.avg_price
        if status.avg_price is not None and status.avg_price > 0:
            return cast(float, status.avg_price)
        return current_avg_price

    def _fill_aggregate_payload(self, fill_aggregate: ExchangeFillAggregate | None) -> dict[str, object]:
        if fill_aggregate is None:
            return {}
        return {
            "exchange_order_id": fill_aggregate.exchange_order_id,
            "fill_count": fill_aggregate.fill_count,
            "quantity": fill_aggregate.quantity,
            "quote_quantity": fill_aggregate.quote_quantity,
            "avg_price": fill_aggregate.avg_price,
            "realized_pnl": fill_aggregate.realized_pnl,
            "commission": fill_aggregate.commission,
        }

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

    def get_by_exchange_trade_id(self, exchange_trade_id: str) -> TradeModel | None:
        statement = select(TradeModel).where(TradeModel.exchange_trade_id == exchange_trade_id)
        return self.session.scalar(statement)

    def create_from_exchange_fill(
        self,
        fill: ExchangeFill,
        *,
        bot_session_id: int | None = None,
        order_id: int | None = None,
    ) -> tuple[TradeModel | None, bool]:
        """Create an idempotent closed-PnL trade from a Binance realized-PnL fill."""
        if not fill.is_closing_fill:
            return None, False
        existing = self.get_by_exchange_trade_id(fill.exchange_trade_id)
        if existing is not None:
            return existing, False

        model = TradeModel(
            bot_session_id=bot_session_id,
            order_id=order_id,
            symbol=fill.symbol,
            side=fill.inferred_position_side,
            quantity=fill.quantity,
            entry_price=fill.inferred_entry_price,
            exit_price=fill.price,
            pnl=fill.realized_pnl,
            pnl_pct=fill.inferred_pnl_pct,
            entry_time=fill.event_time,
            exit_time=fill.event_time,
            exit_reason="exchange_fill",
            fees=fill.commission,
            source="exchange_reconciliation",
            exchange_trade_id=fill.exchange_trade_id,
            exchange_order_id=fill.exchange_order_id,
        )
        self.session.add(model)
        self.session.flush()
        return model, True

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


class ExchangeFillRepository:
    """Persistence operations for raw exchange fills."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_exchange_trade_id(self, exchange_trade_id: str) -> ExchangeFillModel | None:
        statement = select(ExchangeFillModel).where(ExchangeFillModel.exchange_trade_id == exchange_trade_id)
        return self.session.scalar(statement)

    def create_from_fill(
        self,
        fill: ExchangeFill,
        *,
        bot_session_id: int | None = None,
    ) -> tuple[ExchangeFillModel, bool]:
        existing = self.get_by_exchange_trade_id(fill.exchange_trade_id)
        if existing is not None:
            return existing, False

        model = ExchangeFillModel(
            bot_session_id=bot_session_id,
            symbol=fill.symbol,
            exchange_trade_id=fill.exchange_trade_id,
            exchange_order_id=fill.exchange_order_id,
            side=fill.side,
            position_side=fill.position_side,
            price=fill.price,
            quantity=fill.quantity,
            quote_quantity=fill.quote_quantity,
            realized_pnl=fill.realized_pnl,
            commission=fill.commission,
            commission_asset=fill.commission_asset,
            buyer=fill.buyer,
            maker=fill.maker,
            event_time=fill.event_time,
            raw_payload=fill.raw_payload,
        )
        self.session.add(model)
        self.session.flush()
        return model, True

    def list_recent(self, *, symbol: str | None = None, limit: int = 100) -> list[ExchangeFillModel]:
        statement = select(ExchangeFillModel)
        if symbol is not None:
            statement = statement.where(ExchangeFillModel.symbol == symbol)
        statement = statement.order_by(ExchangeFillModel.event_time.desc()).limit(limit)
        return list(self.session.scalars(statement))

    def aggregate_by_order_id(self, exchange_order_id: str) -> ExchangeFillAggregate | None:
        statement = select(ExchangeFillModel).where(ExchangeFillModel.exchange_order_id == exchange_order_id)
        fills = list(self.session.scalars(statement))
        if not fills:
            return None
        return ExchangeFillAggregate(
            exchange_order_id=exchange_order_id,
            fill_count=len(fills),
            quantity=sum(fill.quantity for fill in fills),
            quote_quantity=sum(fill.quote_quantity for fill in fills),
            realized_pnl=sum(fill.realized_pnl for fill in fills),
            commission=sum(fill.commission for fill in fills),
        )


class AccountSnapshotRepository:
    """Persistence operations for live account wallet/equity snapshots."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create_from_snapshot(
        self,
        snapshot: AccountSnapshot,
        *,
        bot_session_id: int | None = None,
    ) -> AccountSnapshotModel:
        model = AccountSnapshotModel(
            bot_session_id=bot_session_id,
            asset=snapshot.asset.upper(),
            wallet_balance=snapshot.wallet_balance,
            unrealized_pnl=snapshot.unrealized_pnl,
            margin_balance=snapshot.margin_balance,
            available_balance=snapshot.available_balance,
            max_withdraw_amount=snapshot.max_withdraw_amount,
            event_time=snapshot.event_time or utc_now(),
            raw_response=snapshot.raw_response,
        )
        self.session.add(model)
        self.session.flush()
        return model

    def latest(self, *, asset: str = "USDT") -> AccountSnapshotModel | None:
        statement = (
            select(AccountSnapshotModel)
            .where(AccountSnapshotModel.asset == asset.upper())
            .order_by(AccountSnapshotModel.event_time.desc(), AccountSnapshotModel.id.desc())
            .limit(1)
        )
        return self.session.scalar(statement)

    def list_recent(self, *, asset: str | None = None, limit: int = 100) -> list[AccountSnapshotModel]:
        statement = select(AccountSnapshotModel)
        if asset is not None:
            statement = statement.where(AccountSnapshotModel.asset == asset.upper())
        statement = statement.order_by(AccountSnapshotModel.event_time.desc(), AccountSnapshotModel.id.desc()).limit(limit)
        return list(self.session.scalars(statement))


class AIReportRepository:
    """Persistence operations for advisory AI trade journal reports."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        symbol: str,
        strategy_name: str,
        event_type: str,
        model: str,
        prompt: str,
        report_text: str,
        input_snapshot: dict[str, object],
        risk_state: dict[str, object],
        market_regime: dict[str, object],
        outcome: dict[str, object],
        raw_response: dict[str, object] | None = None,
        bot_session_id: int | None = None,
        signal_id: int | None = None,
        trade_id: int | None = None,
    ) -> AIReportModel:
        report = AIReportModel(
            bot_session_id=bot_session_id,
            signal_id=signal_id,
            trade_id=trade_id,
            symbol=symbol,
            strategy_name=strategy_name,
            event_type=event_type,
            model=model,
            prompt=prompt,
            report_text=report_text,
            input_snapshot=input_snapshot,
            risk_state=risk_state,
            market_regime=market_regime,
            outcome=outcome,
            raw_response=raw_response or {},
        )
        self.session.add(report)
        self.session.flush()
        return report

    def list_recent(
        self,
        *,
        symbol: str | None = None,
        event_type: str | None = None,
        limit: int = 100,
    ) -> list[AIReportModel]:
        statement = select(AIReportModel)
        if symbol is not None:
            statement = statement.where(AIReportModel.symbol == symbol)
        if event_type is not None:
            statement = statement.where(AIReportModel.event_type == event_type)
        statement = statement.order_by(AIReportModel.created_at.desc()).limit(limit)
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

    def get_open_by_symbol(self, symbol: str) -> PositionModel | None:
        statement = (
            select(PositionModel)
            .where(PositionModel.symbol == symbol)
            .where(PositionModel.status == "open")
            .order_by(PositionModel.opened_at.desc())
        )
        return self.session.scalar(statement)

    def sync_exchange_position(
        self,
        *,
        symbol: str,
        position: Position | None,
        bot_session_id: int | None = None,
    ) -> PositionModel | None:
        current = self.get_open_by_symbol(symbol)
        if position is None:
            for open_position in self.session.scalars(
                select(PositionModel).where(PositionModel.symbol == symbol).where(PositionModel.status == "open")
            ):
                open_position.status = "closed"
                open_position.closed_at = utc_now()
            self.session.flush()
            return None
        if current is None:
            current = PositionModel(
                bot_session_id=bot_session_id,
                symbol=symbol,
                side=position.side.value,
                quantity=position.quantity,
                entry_price=position.entry_price,
                unrealized_pnl=position.unrealized_pnl,
                leverage=position.leverage,
                status="open",
            )
            self.session.add(current)
        else:
            current.side = position.side.value
            current.quantity = position.quantity
            current.entry_price = position.entry_price
            current.unrealized_pnl = position.unrealized_pnl
            current.leverage = position.leverage
        self.session.flush()
        return current


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
