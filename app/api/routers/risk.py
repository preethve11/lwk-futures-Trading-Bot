"""Risk state and kill-switch endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.dependencies import get_app_settings, get_db, require_api_token
from app.api.schemas import (
    KillSwitchRequest,
    PerformanceGateResponse,
    RiskEventResponse,
    RiskStateResponse,
    RiskStateUpdateRequest,
)
from app.api.services import RiskService
from app.core.config import Settings
from app.ops.performance_gate import evaluate_strategy_performance_gate
from app.persistence.models import RiskEventModel
from app.persistence.repositories import RiskEventRepository
from app.persistence.models import RiskStateModel

router = APIRouter(prefix="/risk", tags=["risk"], dependencies=[Depends(require_api_token)])


@router.get("/state", response_model=RiskStateResponse)
def get_risk_state(db: Annotated[Session, Depends(get_db)]) -> RiskStateModel:
    return RiskService(db).get_state()


@router.post("/state", response_model=RiskStateResponse)
async def update_risk_state(
    request_body: RiskStateUpdateRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> RiskStateModel:
    state = RiskService(db).update_state(
        kill_switch_enabled=request_body.kill_switch_enabled,
        manual_pause_enabled=request_body.manual_pause_enabled,
        daily_loss_locked=request_body.daily_loss_locked,
        drawdown_locked=request_body.drawdown_locked,
        reason=request_body.reason,
    )
    await request.app.state.event_bus.broadcast(
        "risk_event",
        {
            "kill_switch_enabled": state.kill_switch_enabled,
            "manual_pause_enabled": state.manual_pause_enabled,
            "daily_loss_locked": state.daily_loss_locked,
            "drawdown_locked": state.drawdown_locked,
            "reason": state.reason,
        },
    )
    return state


@router.post("/kill-switch", response_model=RiskStateResponse)
async def set_kill_switch(
    request_body: KillSwitchRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> RiskStateModel:
    state = RiskService(db).set_kill_switch(enabled=request_body.enabled, reason=request_body.reason)
    await request.app.state.event_bus.broadcast(
        "risk_event",
        {"kill_switch_enabled": state.kill_switch_enabled, "reason": state.reason},
    )
    return state


@router.get("/events", response_model=list[RiskEventResponse])
def list_risk_events(
    db: Annotated[Session, Depends(get_db)],
    symbol: str | None = None,
    limit: int = 100,
) -> list[RiskEventModel]:
    return RiskEventRepository(db).list_recent(symbol=symbol, limit=limit)


@router.get("/performance-gate", response_model=PerformanceGateResponse)
def get_performance_gate(
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> dict[str, object]:
    return evaluate_strategy_performance_gate(db, settings).to_dict()
