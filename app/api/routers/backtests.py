"""Backtest endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_app_settings, get_db, require_api_token
from app.api.schemas import BacktestRunRequest, BacktestRunResponse, BacktestRunResult
from app.api.services import BacktestService
from app.core.config import Settings
from app.persistence.models import BacktestRunModel
from app.persistence.repositories import TradeRepository

router = APIRouter(prefix="/backtests", tags=["backtests"], dependencies=[Depends(require_api_token)])


@router.get("", response_model=list[BacktestRunResponse])
def list_backtests(db: Annotated[Session, Depends(get_db)], limit: int = 100) -> list[BacktestRunModel]:
    return TradeRepository(db).list_backtest_runs(limit=limit)


@router.post("/run", response_model=BacktestRunResult)
def run_backtest(
    request: BacktestRunRequest,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> dict[str, object]:
    try:
        run_model, result = BacktestService(db, settings).run(request)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"backtest_run": run_model, "equity_curve": result.equity_curve}
