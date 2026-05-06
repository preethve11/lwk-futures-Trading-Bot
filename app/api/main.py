"""FastAPI app factory."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.event_bus import LiveEventBus
from app.api.routers import ai_reports, backtests, configs, positions, risk, sessions, signals, trades, ws
from app.api.schemas import HealthResponse
from app.core.config import Settings, get_settings
from app.persistence.database import SessionFactory, create_session_factory, init_db


def create_app(
    settings: Settings | None = None,
    *,
    session_factory: SessionFactory | None = None,
    init_database: bool = True,
) -> FastAPI:
    app_settings = settings or get_settings()
    factory = session_factory or create_session_factory(app_settings.database_url)
    if init_database:
        init_db(factory)

    app = FastAPI(title="LWK Futures Trading Bot API", version="0.5.0")
    if app_settings.api_cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=app_settings.api_cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    app.state.settings = app_settings
    app.state.session_factory = factory
    app.state.db_initialized = init_database
    app.state.event_bus = LiveEventBus()

    @app.get("/health", response_model=HealthResponse, tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(configs.router)
    app.include_router(ai_reports.router)
    app.include_router(backtests.router)
    app.include_router(trades.router)
    app.include_router(positions.router)
    app.include_router(sessions.router)
    app.include_router(risk.router)
    app.include_router(signals.router)
    app.include_router(ws.router)
    return app


app = create_app(init_database=False)
