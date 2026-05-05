"""Trade endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, require_api_token
from app.api.schemas import TradeResponse
from app.persistence.models import TradeModel
from app.persistence.repositories import TradeRepository

router = APIRouter(prefix="/trades", tags=["trades"], dependencies=[Depends(require_api_token)])


@router.get("", response_model=list[TradeResponse])
def list_trades(
    db: Annotated[Session, Depends(get_db)],
    symbol: str | None = None,
    limit: int = 100,
) -> list[TradeModel]:
    return TradeRepository(db).list_recent(symbol=symbol, limit=limit)


@router.get("/{trade_id}", response_model=TradeResponse)
def get_trade(trade_id: int, db: Annotated[Session, Depends(get_db)]) -> TradeModel:
    trade = TradeRepository(db).get(trade_id)
    if trade is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trade not found")
    return trade
