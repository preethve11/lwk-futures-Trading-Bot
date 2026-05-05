"""Signal endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, require_api_token
from app.api.schemas import SignalResponse
from app.persistence.models import SignalModel
from app.persistence.repositories import SignalRepository

router = APIRouter(prefix="/signals", tags=["signals"], dependencies=[Depends(require_api_token)])


@router.get("", response_model=list[SignalResponse])
def list_signals(
    db: Annotated[Session, Depends(get_db)],
    symbol: str | None = None,
    limit: int = 100,
) -> list[SignalModel]:
    return SignalRepository(db).list_recent(symbol=symbol, limit=limit)
