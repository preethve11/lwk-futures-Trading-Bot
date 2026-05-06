"""FastAPI app factory."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from time import perf_counter

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.api.event_bus import LiveEventBus
from app.api.routers import (
    ai_reports,
    backtests,
    configs,
    exchange_fills,
    monitoring,
    positions,
    risk,
    sessions,
    signals,
    trades,
    ws,
)
from app.api.schemas import HealthResponse
from app.core.config import Settings, get_settings
from app.monitoring.metrics import AppMetrics
from app.persistence.database import SessionFactory, create_session_factory, init_db


def create_app(
    settings: Settings | None = None,
    *,
    session_factory: SessionFactory | None = None,
    init_database: bool = True,
) -> FastAPI:
    app_settings = settings or get_settings()
    factory = session_factory or create_session_factory(app_settings.database_url)
    database_initialized = False
    if init_database and app_settings.database_auto_create_tables:
        init_db(factory)
        database_initialized = True
    elif not app_settings.database_auto_create_tables:
        database_initialized = True

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
    app.state.db_initialized = database_initialized
    app.state.event_bus = LiveEventBus()
    app.state.metrics = AppMetrics(version=app.version)

    @app.middleware("http")
    async def record_metrics(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        started_at = perf_counter()
        response = await call_next(request)
        metrics = getattr(request.app.state, "metrics", None)
        if isinstance(metrics, AppMetrics):
            route = request.scope.get("route")
            path = getattr(route, "path", request.url.path)
            metrics.record_http_request(
                method=request.method,
                path=str(path),
                status_code=response.status_code,
                started_at=started_at,
            )
        return response

    @app.get("/health", response_model=HealthResponse, tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(monitoring.router)
    app.include_router(configs.router)
    app.include_router(ai_reports.router)
    app.include_router(exchange_fills.router)
    app.include_router(backtests.router)
    app.include_router(trades.router)
    app.include_router(positions.router)
    app.include_router(sessions.router)
    app.include_router(risk.router)
    app.include_router(signals.router)
    app.include_router(ws.router)
    return app


app = create_app(init_database=False)
