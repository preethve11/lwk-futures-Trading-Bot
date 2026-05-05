"""Configuration snapshot endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, require_api_token
from app.api.schemas import ConfigCreateRequest, ConfigResponse
from app.persistence.models import ConfigModel
from app.persistence.repositories import ConfigRepository

router = APIRouter(prefix="/configs", tags=["configs"], dependencies=[Depends(require_api_token)])


@router.get("", response_model=list[ConfigResponse])
def list_configs(db: Annotated[Session, Depends(get_db)]) -> list[ConfigModel]:
    return ConfigRepository(db).list_all()


@router.post("", response_model=ConfigResponse)
def create_config(request: ConfigCreateRequest, db: Annotated[Session, Depends(get_db)]) -> ConfigModel:
    return ConfigRepository(db).upsert(name=request.name, payload=request.payload, is_active=request.is_active)
