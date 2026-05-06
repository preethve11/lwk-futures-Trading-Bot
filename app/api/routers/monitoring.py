"""Health, readiness, and Prometheus metrics endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Request, Response, status
from prometheus_client import CONTENT_TYPE_LATEST

from app.api.dependencies import get_app_settings, get_session_factory
from app.api.schemas import ReadinessResponse
from app.core.config import Settings
from app.monitoring.metrics import AppMetrics, check_database_readiness

router = APIRouter(tags=["monitoring"])


@router.get("/ready", response_model=ReadinessResponse)
def readiness(request: Request, response: Response) -> ReadinessResponse:
    settings = get_app_settings(request)
    details: dict[str, str] = {}
    status_value = "ok"
    if settings.readiness_check_database:
        check = check_database_readiness(get_session_factory(request))
        details.update(check.details)
        status_value = check.status
    if status_value != "ok":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(status=status_value, details=details)


@router.get("/metrics", include_in_schema=False)
def metrics(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    x_metrics_token: Annotated[str | None, Header()] = None,
) -> Response:
    settings = get_app_settings(request)
    _authorize_metrics(settings, authorization=authorization, x_metrics_token=x_metrics_token)
    app_metrics = getattr(request.app.state, "metrics", None)
    if not isinstance(app_metrics, AppMetrics):
        app_metrics = AppMetrics()
        request.app.state.metrics = app_metrics
    session_factory = get_session_factory(request) if settings.metrics_include_database else None
    return Response(
        content=app_metrics.render(session_factory=session_factory, include_database=settings.metrics_include_database),
        media_type=CONTENT_TYPE_LATEST,
    )


def _authorize_metrics(settings: Settings, *, authorization: str | None, x_metrics_token: str | None) -> None:
    if not settings.metrics_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Metrics are disabled")

    expected = settings.metrics_token
    if not expected:
        if settings.app_env == "production":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Metrics token is required in production",
            )
        return

    presented = x_metrics_token or ""
    bearer_prefix = "Bearer "
    if authorization and authorization.startswith(bearer_prefix):
        presented = authorization[len(bearer_prefix):]
    if presented != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid metrics token")
