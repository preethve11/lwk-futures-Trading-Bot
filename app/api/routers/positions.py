"""Position snapshot endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, require_api_token
from app.api.schemas import PositionResponse
from app.persistence.models import PositionModel
from app.persistence.repositories import PositionRepository

router = APIRouter(prefix="/positions", tags=["positions"], dependencies=[Depends(require_api_token)])


@router.get("", response_model=list[PositionResponse])
def list_positions(
    db: Annotated[Session, Depends(get_db)],
    symbol: str | None = None,
    limit: int = 100,
) -> list[PositionModel]:
    return PositionRepository(db).list_recent(symbol=symbol, limit=limit)
