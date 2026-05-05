"""FastAPI dependency wiring."""

from __future__ import annotations

from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.persistence.database import SessionFactory, create_session_factory, init_db


def get_app_settings(request: Request) -> Settings:
    settings = getattr(request.app.state, "settings", None)
    if isinstance(settings, Settings):
        return settings
    return get_settings()


def get_session_factory(request: Request) -> SessionFactory:
    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        settings = get_app_settings(request)
        factory = create_session_factory(settings.database_url)
        request.app.state.session_factory = factory
    if not bool(getattr(request.app.state, "db_initialized", False)):
        init_db(factory)
        request.app.state.db_initialized = True
    return factory


def get_db(factory: Annotated[SessionFactory, Depends(get_session_factory)]) -> Generator[Session, None, None]:
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def require_api_token(
    settings: Annotated[Settings, Depends(get_app_settings)],
    authorization: Annotated[str | None, Header()] = None,
    x_api_token: Annotated[str | None, Header()] = None,
) -> None:
    """Require configured API token; local empty-token mode remains open for development/tests."""
    if not settings.api_token:
        if settings.app_env == "production":
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="API token is not configured")
        return

    bearer_prefix = "Bearer "
    presented = x_api_token or ""
    if authorization and authorization.startswith(bearer_prefix):
        presented = authorization[len(bearer_prefix):]
    if presented != settings.api_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API token")
