"""Risk state and kill-switch endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, require_api_token
from app.api.schemas import KillSwitchRequest, RiskStateResponse
from app.api.services import RiskService
from app.persistence.models import RiskStateModel

router = APIRouter(prefix="/risk", tags=["risk"], dependencies=[Depends(require_api_token)])


@router.get("/state", response_model=RiskStateResponse)
def get_risk_state(db: Annotated[Session, Depends(get_db)]) -> RiskStateModel:
    return RiskService(db).get_state()


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
