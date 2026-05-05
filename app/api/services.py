"""API service layer built on repositories and worker primitives."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
from sqlalchemy.orm import Session

from app.api.schemas import BacktestRunRequest
from app.core.config import Settings
from app.persistence.models import BacktestRunModel, BotSessionModel, RiskStateModel
from app.persistence.repositories import BotSessionRepository, RiskStateRepository, TradeRepository
from app.strategies.registry import create_default_strategy_registry
from trading_bot.backtesting.engine import BacktestEngine, BacktestResult
from trading_bot.risk.manager import RiskManager


class SessionService:
    """API-facing session lifecycle operations."""

    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    def start(self, *, mode: str, strategy_name: str | None, symbol: str | None, timeframe: str | None) -> BotSessionModel:
        return BotSessionRepository(self.session).create(
            mode=mode,
            strategy_name=strategy_name or self.settings.strategy_name,
            symbol=symbol or self.settings.symbol,
            timeframe=timeframe or self.settings.timeframe,
            config_snapshot={"source": "api"},
        )

    def stop(self, *, session_id: int, status: str = "stopped") -> BotSessionModel:
        return BotSessionRepository(self.session).finish(session_id, status=status)


class RiskService:
    """API-facing risk state operations."""

    def __init__(self, session: Session) -> None:
        self.repository = RiskStateRepository(session)

    def get_state(self) -> RiskStateModel:
        return self.repository.get_or_create()

    def set_kill_switch(self, *, enabled: bool, reason: str) -> RiskStateModel:
        return self.repository.set_kill_switch(enabled=enabled, reason=reason)


class BacktestService:
    """Runs API-requested backtests and persists results through repositories."""

    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    def run(self, request: BacktestRunRequest) -> tuple[BacktestRunModel, BacktestResult]:
        if not request.candles:
            raise ValueError("API backtest run requires inline candles for now")

        df = pd.DataFrame([candle.model_dump() for candle in request.candles])
        symbol = request.symbol or self.settings.symbol
        timeframe = request.timeframe or self.settings.timeframe
        strategy = create_default_strategy_registry().create(self.settings.strategy_name, self.settings)
        risk_manager = RiskManager(
            risk_per_trade_usd=self.settings.risk_per_trade_usd,
            max_daily_loss_usd=self.settings.max_daily_loss_usd,
            max_drawdown_pct=self.settings.max_drawdown_pct,
            min_notional=self.settings.min_notional,
            max_position_pct_capital=self.settings.max_position_pct_capital,
            min_risk_reward=self.settings.min_risk_reward,
            use_atr_position_cap=self.settings.use_atr_position_cap,
            trailing_stop_atr_mult=self.settings.trailing_stop_atr_mult,
            symbol_info=None,
        )
        engine = BacktestEngine(
            strategy=strategy,
            risk_manager=risk_manager,
            initial_capital=self.settings.backtest_initial_capital,
            slippage_bps=self.settings.slippage_bps,
            fee_bps=self.settings.fee_bps,
        )
        result = engine.run(df, symbol=symbol, start_date=request.start_date, end_date=request.end_date)
        if result.metrics is None:
            raise ValueError("Backtest metrics were not produced")
        final_capital = result.equity_curve[-1] if result.equity_curve else self.settings.backtest_initial_capital
        run_model = TradeRepository(self.session).create_backtest_run(
            strategy_name=self.settings.strategy_name,
            symbol=symbol,
            timeframe=timeframe,
            initial_capital=self.settings.backtest_initial_capital,
            final_capital=final_capital,
            metrics=result.metrics,
            start_date=_coerce_datetime(request.start_date),
            end_date=_coerce_datetime(request.end_date),
            config_snapshot={"source": "api", "candles": len(request.candles)},
        )
        for trade in result.trades:
            TradeRepository(self.session).create_from_trade(trade, source="backtest")
        return run_model, result


def _coerce_datetime(value: str | datetime | None) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
