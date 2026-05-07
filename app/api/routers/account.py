"""Account wallet/equity snapshot endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, require_api_token
from app.api.schemas import AccountSnapshotResponse
from app.persistence.models import AccountSnapshotModel
from app.persistence.repositories import AccountSnapshotRepository

router = APIRouter(prefix="/account", tags=["account"], dependencies=[Depends(require_api_token)])


@router.get("/snapshots", response_model=list[AccountSnapshotResponse])
def list_account_snapshots(
    db: Annotated[Session, Depends(get_db)],
    asset: str | None = None,
    limit: int = 100,
) -> list[AccountSnapshotModel]:
    return AccountSnapshotRepository(db).list_recent(asset=asset, limit=limit)
