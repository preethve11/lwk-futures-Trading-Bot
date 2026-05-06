"""Pydantic schemas for API requests and responses."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    status: str


class ConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    payload: dict[str, Any]
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ConfigCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    payload: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = False


class BacktestRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: str
    strategy_name: str
    symbol: str
    timeframe: str
    start_date: datetime | None
    end_date: datetime | None
    initial_capital: float
    final_capital: float
    total_trades: int
    total_return_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown_pct: float
    win_rate: float
    profit_factor: float
    expectancy: float
    config_snapshot: dict[str, Any]
    created_at: datetime


class CandleInput(BaseModel):
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class BacktestRunRequest(BaseModel):
    symbol: str | None = None
    timeframe: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    candles: list[CandleInput] = Field(default_factory=list)


class BacktestRunResult(BaseModel):
    backtest_run: BacktestRunResponse
    equity_curve: list[float]


class MultiBacktestRunRequest(BaseModel):
    symbols: list[str] = Field(default_factory=list)
    timeframe: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    candles_by_symbol: dict[str, list[CandleInput]] = Field(default_factory=dict)


class BacktestReportResponse(BaseModel):
    symbol: str
    timeframe: str
    initial_capital: float
    final_capital: float
    total_pnl: float
    total_trades: int
    run_id: str | None = None
    metrics: dict[str, Any]
    equity_curve: list[float]


class MultiBacktestRunResult(BaseModel):
    aggregate: BacktestReportResponse
    symbols: list[BacktestReportResponse]


class TradeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    bot_session_id: int | None
    signal_id: int | None
    order_id: int | None
    symbol: str
    side: str
    quantity: float
    entry_price: float
    exit_price: float
    pnl: float
    pnl_pct: float
    entry_time: datetime
    exit_time: datetime
    exit_reason: str
    fees: float
    slippage_usd: float
    source: str
    created_at: datetime


class SignalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    bot_session_id: int | None
    symbol: str
    strategy_name: str
    side: str
    entry_price: float
    stop_price: float
    take_profit_price: float
    quantity: float
    timestamp: datetime
    status: str
    reason: str | None
    payload: dict[str, Any]
    created_at: datetime


class SessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: str
    mode: str
    strategy_name: str
    symbol: str
    timeframe: str
    status: str
    started_at: datetime
    ended_at: datetime | None
    config_snapshot: dict[str, Any]


class SessionStartRequest(BaseModel):
    mode: str = "paper"
    strategy_name: str | None = None
    symbol: str | None = None
    timeframe: str | None = None


class SessionStopRequest(BaseModel):
    session_id: int
    status: str = "stopped"


class RiskStateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kill_switch_enabled: bool
    manual_pause_enabled: bool
    daily_loss_locked: bool
    drawdown_locked: bool
    reason: str
    updated_at: datetime


class KillSwitchRequest(BaseModel):
    enabled: bool = True
    reason: str = ""


class RiskStateUpdateRequest(BaseModel):
    kill_switch_enabled: bool | None = None
    manual_pause_enabled: bool | None = None
    daily_loss_locked: bool | None = None
    drawdown_locked: bool | None = None
    reason: str | None = None


class RiskEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    bot_session_id: int | None
    symbol: str
    event_type: str
    severity: str
    reason: str
    payload: dict[str, Any]
    created_at: datetime


class AIReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    bot_session_id: int | None
    signal_id: int | None
    trade_id: int | None
    symbol: str
    strategy_name: str
    event_type: str
    model: str
    prompt: str
    report_text: str
    input_snapshot: dict[str, Any]
    risk_state: dict[str, Any]
    market_regime: dict[str, Any]
    outcome: dict[str, Any]
    raw_response: dict[str, Any]
    created_at: datetime


class PositionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    bot_session_id: int | None
    symbol: str
    side: str
    quantity: float
    entry_price: float
    unrealized_pnl: float
    leverage: int
    status: str
    opened_at: datetime
    closed_at: datetime | None


class LiveEvent(BaseModel):
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
