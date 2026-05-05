"""Live trading worker orchestration."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

import pandas as pd

from app.core.config import Settings
from app.core.security import assert_live_trading_allowed
from app.persistence.database import SessionFactory, create_session_factory, init_db, session_scope
from app.persistence.repositories import (
    BotSessionRepository,
    OrderRepository,
    RiskEventRepository,
    RiskStateRepository,
    SignalRepository,
)
from app.strategies.registry import StrategyRegistry, create_default_strategy_registry
from app.workers.reconciliation import ReconciliationOutcome, ReconciliationWorker
from trading_bot.core.types import Signal
from trading_bot.execution.base import ExecutionClient, OrderResult
from trading_bot.execution.binance_futures import BinanceFuturesClient
from trading_bot.risk.manager import RiskManager
from trading_bot.utils.alerts import AlertQueue, AlertSeverity
from trading_bot.utils.timeframes import timeframe_minutes


class LiveTrader:
    """Coordinates strategy, risk, execution, and live-loop state."""

    def __init__(
        self,
        settings: Settings,
        *,
        strategy_registry: StrategyRegistry | None = None,
        client: ExecutionClient | None = None,
        session_factory: SessionFactory | None = None,
        alert_queue: AlertQueue | None = None,
    ) -> None:
        self.settings = settings
        self.strategy_registry = strategy_registry or create_default_strategy_registry()
        self.client = client
        self.session_factory = session_factory
        self.alert_queue = alert_queue or AlertQueue(
            bot_token=settings.telegram_bot_token,
            chat_id=settings.telegram_chat_id,
        )
        self.logger = logging.getLogger("trading_bot.live_trader")

    def run_forever(self) -> int:
        """Run the live trading loop until interrupted."""
        assert_live_trading_allowed(self.settings)
        client = self.client or self._create_client()
        client.set_leverage(self.settings.symbol, self.settings.leverage)

        symbol_info = client.get_symbol_info(self.settings.symbol)
        risk_manager = self._create_risk_manager(symbol_info)
        strategy = self.strategy_registry.create(self.settings.strategy_name, self.settings)
        session_factory = self._create_runtime_session_factory()
        bot_session_id = self._start_bot_session(session_factory)
        reconciliation_worker = ReconciliationWorker(client, self.alert_queue)
        cooldown_s = timeframe_minutes(self.settings.timeframe) * 60
        last_signal_ts = 0.0
        last_hourly = datetime.now(timezone.utc)

        self.alert_queue.enqueue(
            AlertSeverity.INFO,
            "Trading bot starting",
            {
                "symbol": self.settings.symbol,
                "testnet": self.settings.use_testnet,
                "leverage": self.settings.leverage,
            },
        )

        try:
            while True:
                try:
                    daily_loss = self._sync_daily_loss(client, risk_manager)
                    if not risk_manager.check_daily_loss():
                        self.logger.warning("Daily loss cap reached", extra={"symbol": self.settings.symbol})
                        self.alert_queue.enqueue(
                            AlertSeverity.CRITICAL,
                            "Daily loss cap reached",
                            {"symbol": self.settings.symbol, "daily_loss": daily_loss},
                        )
                        self._record_risk_event(
                            session_factory,
                            bot_session_id,
                            event_type="daily_loss_cap",
                            severity="warning",
                            reason="Daily loss cap reached",
                        )
                        time.sleep(60)
                        continue

                    if self._risk_state_blocks_trading(session_factory):
                        self.logger.warning("Trading paused by persisted risk state", extra={"symbol": self.settings.symbol})
                        time.sleep(5)
                        continue

                    position = client.get_open_position(self.settings.symbol)
                    if position and position.quantity > 0:
                        self.logger.info("Position open, waiting", extra={"symbol": self.settings.symbol})
                        time.sleep(5)
                        if (datetime.now(timezone.utc) - last_hourly) >= timedelta(minutes=55):
                            self.alert_queue.enqueue(
                                AlertSeverity.INFO,
                                "Hourly position status",
                                {
                                    "symbol": self.settings.symbol,
                                    "quantity": position.quantity,
                                    "entry_price": position.entry_price,
                                    "daily_loss": round(daily_loss, 2),
                                },
                            )
                            last_hourly = datetime.now(timezone.utc)
                        continue

                    if time.time() - last_signal_ts < cooldown_s:
                        time.sleep(1)
                        continue

                    df = client.get_klines(self.settings.symbol, self.settings.timeframe, limit=300)
                    df = strategy.compute_indicators(df)
                    raw = strategy.get_signal(df)
                    if raw is None:
                        time.sleep(1)
                        continue

                    prev = df.iloc[-2]
                    atr = float(prev["atr"]) if not pd.isna(prev.get("atr")) else 0.0
                    result = risk_manager.validate_signal(
                        raw.entry_price,
                        raw.stop_price,
                        raw.take_profit_price,
                        raw.side,
                        atr,
                        None,
                    )
                    if not result.allowed or result.quantity <= 0:
                        self.logger.info(
                            "Signal rejected by risk manager",
                            extra={"symbol": self.settings.symbol, "reason": result.reason},
                        )
                        self._record_risk_event(
                            session_factory,
                            bot_session_id,
                            event_type="signal_rejected",
                            reason=result.reason or "",
                            payload={"side": raw.side.value, "entry_price": raw.entry_price},
                        )
                        time.sleep(1)
                        continue

                    signal = Signal(
                        side=raw.side,
                        entry_price=raw.entry_price,
                        stop_price=raw.stop_price,
                        take_profit_price=raw.take_profit_price,
                        quantity=result.quantity,
                        timestamp=raw.timestamp,
                        metadata=raw.metadata,
                    )
                    order_result = client.place_market_and_sl_tp(self.settings.symbol, signal)
                    reconciliation = reconciliation_worker.reconcile(
                        symbol=self.settings.symbol,
                        signal=signal,
                        order_result=order_result,
                    )
                    _, order_id = self._record_live_signal(session_factory, bot_session_id, signal)
                    self._record_order_result(session_factory, order_id, order_result)
                    self._record_reconciliation_result(
                        session_factory,
                        bot_session_id,
                        order_id,
                        reconciliation,
                    )
                    if order_result.success:
                        last_signal_ts = time.time()
                    if reconciliation.protected_order.protected:
                        self.alert_queue.enqueue(
                            AlertSeverity.INFO,
                            "Protected entry accepted",
                            {
                                "symbol": self.settings.symbol,
                                "side": raw.side.value,
                                "quantity": result.quantity,
                                "entry": order_result.avg_price or raw.entry_price,
                            },
                        )
                    time.sleep(1)
                except KeyboardInterrupt:
                    self.logger.info("Shutdown by user")
                    self.alert_queue.enqueue(AlertSeverity.INFO, "Trading bot stopped by user")
                    break
                except Exception as exc:
                    self.logger.exception("Live loop error", extra={"error": str(exc)})
                    self.alert_queue.enqueue(AlertSeverity.CRITICAL, "Live loop error", {"error": str(exc)})
                    time.sleep(5)
        finally:
            self._finish_bot_session(session_factory, bot_session_id, status="stopped")
            self.alert_queue.stop(drain=True)
        return 0

    def _create_client(self) -> ExecutionClient:
        if not self.settings.active_binance_api_key or not self.settings.active_binance_api_secret:
            raise RuntimeError("Missing active Binance API key or secret")
        return BinanceFuturesClient(
            self.settings.active_binance_api_key,
            self.settings.active_binance_api_secret,
            testnet=self.settings.use_testnet,
        )

    def _create_risk_manager(self, symbol_info: dict[str, object] | None) -> RiskManager:
        return RiskManager(
            risk_per_trade_usd=self.settings.risk_per_trade_usd,
            max_daily_loss_usd=self.settings.max_daily_loss_usd,
            max_drawdown_pct=self.settings.max_drawdown_pct,
            min_notional=self.settings.min_notional,
            max_position_pct_capital=self.settings.max_position_pct_capital,
            min_risk_reward=self.settings.min_risk_reward,
            use_atr_position_cap=self.settings.use_atr_position_cap,
            trailing_stop_atr_mult=self.settings.trailing_stop_atr_mult,
            symbol_info=symbol_info,
        )

    def _sync_daily_loss(self, client: ExecutionClient, risk_manager: RiskManager) -> float:
        trades = client.fetch_recent_trades(self.settings.symbol, limit=500)
        now_date = datetime.now(timezone.utc).date()
        day_start_ts = int(datetime.combine(now_date, datetime.min.time(), tzinfo=timezone.utc).timestamp() * 1000)
        realized = sum(
            float(trade.get("realizedPnl", 0))
            for trade in trades
            if int(trade.get("time", 0)) >= day_start_ts
        )
        daily_loss = max(0.0, -realized)
        risk_manager.set_daily_loss(daily_loss, now_date)
        return daily_loss

    def _create_runtime_session_factory(self) -> SessionFactory:
        session_factory = self.session_factory or create_session_factory(self.settings.database_url)
        try:
            init_db(session_factory)
        except Exception as exc:
            self.logger.exception("Could not initialize persistence database", extra={"error": str(exc)})
        return session_factory

    def _start_bot_session(self, session_factory: SessionFactory) -> int | None:
        try:
            with session_scope(session_factory) as session:
                bot_session = BotSessionRepository(session).create(
                    mode="live",
                    strategy_name=self.settings.strategy_name,
                    symbol=self.settings.symbol,
                    timeframe=self.settings.timeframe,
                    config_snapshot={
                        "use_testnet": self.settings.use_testnet,
                        "leverage": self.settings.leverage,
                        "risk_per_trade_usd": self.settings.risk_per_trade_usd,
                    },
                )
                return bot_session.id
        except Exception as exc:
            self.logger.exception("Could not persist live bot session", extra={"error": str(exc)})
            return None

    def _finish_bot_session(self, session_factory: SessionFactory, bot_session_id: int | None, *, status: str) -> None:
        if bot_session_id is None:
            return
        try:
            with session_scope(session_factory) as session:
                BotSessionRepository(session).finish(bot_session_id, status=status)
        except Exception as exc:
            self.logger.exception("Could not finish live bot session", extra={"error": str(exc)})

    def _record_live_signal(
        self,
        session_factory: SessionFactory,
        bot_session_id: int | None,
        signal: Signal,
    ) -> tuple[int | None, int | None]:
        try:
            with session_scope(session_factory) as session:
                signal_model = SignalRepository(session).create_from_signal(
                    signal,
                    symbol=self.settings.symbol,
                    strategy_name=self.settings.strategy_name,
                    bot_session_id=bot_session_id,
                )
                order_model = OrderRepository(session).create_pending(
                    symbol=self.settings.symbol,
                    side=signal.side.value,
                    quantity=signal.quantity,
                    signal_id=signal_model.id,
                    bot_session_id=bot_session_id,
                )
                return signal_model.id, order_model.id
        except Exception as exc:
            self.logger.exception("Could not persist live signal", extra={"error": str(exc)})
            return None, None

    def _record_order_result(
        self,
        session_factory: SessionFactory,
        order_id: int | None,
        order_result: OrderResult,
    ) -> None:
        if order_id is None:
            return
        try:
            with session_scope(session_factory) as session:
                OrderRepository(session).apply_order_result(order_id, order_result)
        except Exception as exc:
            self.logger.exception("Could not persist order result", extra={"error": str(exc)})

    def _record_reconciliation_result(
        self,
        session_factory: SessionFactory,
        bot_session_id: int | None,
        order_id: int | None,
        reconciliation: ReconciliationOutcome,
    ) -> None:
        try:
            with session_scope(session_factory) as session:
                if order_id is not None:
                    OrderRepository(session).apply_protected_order_result(
                        order_id,
                        reconciliation.protected_order,
                        emergency_close_order_id=reconciliation.emergency_close_order_id,
                    )
                risk_events = RiskEventRepository(session)
                for event in reconciliation.events:
                    payload = dict(event.payload)
                    payload["attempts"] = reconciliation.attempts
                    if order_id is not None:
                        payload["order_id"] = order_id
                    risk_events.create(
                        symbol=self.settings.symbol,
                        event_type=event.event_type,
                        severity=event.severity,
                        reason=event.reason,
                        bot_session_id=bot_session_id,
                        payload=payload,
                    )
        except Exception as exc:
            self.logger.exception("Could not persist reconciliation result", extra={"error": str(exc)})

    def _record_risk_event(
        self,
        session_factory: SessionFactory,
        bot_session_id: int | None,
        *,
        event_type: str,
        severity: str = "info",
        reason: str = "",
        payload: dict[str, object] | None = None,
    ) -> None:
        try:
            with session_scope(session_factory) as session:
                RiskEventRepository(session).create(
                    symbol=self.settings.symbol,
                    event_type=event_type,
                    severity=severity,
                    reason=reason,
                    bot_session_id=bot_session_id,
                    payload=payload,
                )
        except Exception as exc:
            self.logger.exception("Could not persist risk event", extra={"error": str(exc)})

    def _risk_state_blocks_trading(self, session_factory: SessionFactory) -> bool:
        try:
            with session_scope(session_factory) as session:
                state = RiskStateRepository(session).get_or_create()
                blocked = (
                    state.kill_switch_enabled
                    or state.manual_pause_enabled
                    or state.daily_loss_locked
                    or state.drawdown_locked
                )
                if blocked:
                    self.alert_queue.enqueue(
                        AlertSeverity.CRITICAL,
                        "Trading paused by risk state",
                        {"symbol": self.settings.symbol, "reason": state.reason},
                    )
                return blocked
        except Exception as exc:
            self.logger.exception("Could not read risk state", extra={"error": str(exc)})
            return False
