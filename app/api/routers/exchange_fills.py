"""Exchange fill ledger endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, require_api_token
from app.api.schemas import ExchangeFillResponse
from app.persistence.models import ExchangeFillModel
from app.persistence.repositories import ExchangeFillRepository

router = APIRouter(prefix="/exchange-fills", tags=["exchange-fills"], dependencies=[Depends(require_api_token)])


@router.get("", response_model=list[ExchangeFillResponse])
def list_exchange_fills(
    db: Annotated[Session, Depends(get_db)],
    symbol: str | None = None,
    limit: int = 100,
) -> list[ExchangeFillModel]:
    return ExchangeFillRepository(db).list_recent(symbol=symbol, limit=limit)
