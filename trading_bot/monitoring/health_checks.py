"""Infrastructure health checks for operator dashboards."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text

from app.persistence.database import SessionFactory


@dataclass(frozen=True)
class HealthCheckResult:
    """One dependency health-check result."""

    name: str
    healthy: bool
    detail: str


def check_database(session_factory: SessionFactory) -> HealthCheckResult:
    """Verify that the configured database can execute a simple query."""
    try:
        with session_factory() as session:
            session.execute(text("SELECT 1"))
        return HealthCheckResult(name="database", healthy=True, detail="Database query succeeded")
    except Exception as exc:
        return HealthCheckResult(name="database", healthy=False, detail=str(exc))
