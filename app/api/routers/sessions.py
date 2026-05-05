"""Bot session endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.dependencies import get_app_settings, get_db, require_api_token
from app.api.schemas import SessionResponse, SessionStartRequest, SessionStopRequest
from app.api.services import SessionService
from app.core.config import Settings
from app.persistence.models import BotSessionModel
from app.persistence.repositories import BotSessionRepository

router = APIRouter(prefix="/sessions", tags=["sessions"], dependencies=[Depends(require_api_token)])


@router.get("", response_model=list[SessionResponse])
def list_sessions(db: Annotated[Session, Depends(get_db)], limit: int = 100) -> list[BotSessionModel]:
    return BotSessionRepository(db).list_recent(limit=limit)


@router.post("/start", response_model=SessionResponse)
async def start_session(
    request_body: SessionStartRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> BotSessionModel:
    session_model = SessionService(db, settings).start(
        mode=request_body.mode,
        strategy_name=request_body.strategy_name,
        symbol=request_body.symbol,
        timeframe=request_body.timeframe,
    )
    await request.app.state.event_bus.broadcast(
        "session_started",
        {"id": session_model.id, "symbol": session_model.symbol, "mode": session_model.mode},
    )
    return session_model


@router.post("/stop", response_model=SessionResponse)
async def stop_session(
    request_body: SessionStopRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> BotSessionModel:
    session_model = SessionService(db, settings).stop(session_id=request_body.session_id, status=request_body.status)
    await request.app.state.event_bus.broadcast(
        "session_stopped",
        {"id": session_model.id, "status": session_model.status},
    )
    return session_model
