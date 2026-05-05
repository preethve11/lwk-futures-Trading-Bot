"""SQLAlchemy engine and session helpers."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.persistence.models import Base

SessionFactory = sessionmaker[Session]


def create_session_factory(database_url: str, *, echo: bool = False) -> SessionFactory:
    """Create a SQLAlchemy session factory for the configured database URL."""
    connect_args: dict[str, object] = {}
    engine_kwargs: dict[str, object] = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        if database_url in {"sqlite:///:memory:", "sqlite://"}:
            engine_kwargs["poolclass"] = StaticPool
    engine = create_engine(database_url, echo=echo, future=True, connect_args=connect_args, **engine_kwargs)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db(engine_or_session_factory: Engine | SessionFactory) -> None:
    """Create database tables for all persistence models."""
    bind = engine_or_session_factory if isinstance(engine_or_session_factory, Engine) else engine_or_session_factory.kw["bind"]
    if not isinstance(bind, Engine):
        raise TypeError("init_db requires an Engine or sessionmaker bound to an Engine")
    Base.metadata.create_all(bind)


@contextmanager
def session_scope(session_factory: SessionFactory) -> Generator[Session, None, None]:
    """Provide a transactional session scope."""
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
