"""AI trade journal report endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, require_api_token
from app.api.schemas import AIReportResponse
from app.persistence.models import AIReportModel
from app.persistence.repositories import AIReportRepository

router = APIRouter(prefix="/ai-reports", tags=["ai-reports"], dependencies=[Depends(require_api_token)])


@router.get("", response_model=list[AIReportResponse])
def list_ai_reports(
    db: Annotated[Session, Depends(get_db)],
    symbol: str | None = None,
    event_type: str | None = None,
    limit: int = 100,
) -> list[AIReportModel]:
    return AIReportRepository(db).list_recent(symbol=symbol, event_type=event_type, limit=limit)
