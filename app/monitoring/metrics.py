"""Prometheus metrics and readiness probes for the trading platform."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError

from app.persistence.database import SessionFactory, session_scope
from app.persistence.models import (
    AIReportModel,
    BacktestRunModel,
    BotSessionModel,
    ExchangeFillModel,
    OrderLifecycleState,
    OrderModel,
    PositionModel,
    RiskEventModel,
    RiskStateModel,
    SignalModel,
    TradeModel,
)


@dataclass(frozen=True)
class ReadinessCheck:
    """Result of a dependency readiness check."""

    status: str
    details: dict[str, str] = field(default_factory=dict)


class AppMetrics:
    """Application-owned Prometheus registry.

    A per-app registry avoids duplicate metric registration when tests construct
    multiple FastAPI app instances in one process.
    """

    def __init__(self, *, service_name: str = "lwk-futures-trading-bot", version: str = "0.6.0") -> None:
        self.registry = CollectorRegistry(auto_describe=True)
        self._http_requests = Counter(
            "trading_bot_http_requests_total",
            "HTTP requests handled by the trading bot API.",
            ("method", "path", "status_code"),
            registry=self.registry,
        )
        self._http_duration = Histogram(
            "trading_bot_http_request_duration_seconds",
            "HTTP request latency for the trading bot API.",
            ("method", "path"),
            registry=self.registry,
        )
        self._build_info = Gauge(
            "trading_bot_build_info",
            "Static build information for the trading bot service.",
            ("service", "version"),
            registry=self.registry,
        )
        self._open_sessions = Gauge(
            "trading_bot_open_sessions",
            "Bot sessions currently marked as running.",
            registry=self.registry,
        )
        self._open_positions = Gauge(
            "trading_bot_open_positions",
            "Persisted positions currently marked as open.",
            registry=self.registry,
        )
        self._unprotected_orders = Gauge(
            "trading_bot_unprotected_orders",
            "Orders that require manual review or failed protection.",
            registry=self.registry,
        )
        self._risk_events = Gauge(
            "trading_bot_risk_events_total",
            "Persisted risk event count by severity.",
            ("severity",),
            registry=self.registry,
        )
        self._risk_state = Gauge(
            "trading_bot_risk_state",
            "Operator risk-control flags; 1 means enabled or locked.",
            ("flag",),
            registry=self.registry,
        )
        self._records = Gauge(
            "trading_bot_persisted_records_total",
            "Persisted record count by table.",
            ("table",),
            registry=self.registry,
        )
        self._db_readiness = Gauge(
            "trading_bot_database_ready",
            "Database readiness; 1 means the latest readiness query succeeded.",
            registry=self.registry,
        )
        self._build_info.labels(service=service_name, version=version).set(1)

    def record_http_request(self, *, method: str, path: str, status_code: int, started_at: float) -> None:
        duration_seconds = perf_counter() - started_at
        labels = {
            "method": method,
            "path": path,
            "status_code": str(status_code),
        }
        self._http_requests.labels(**labels).inc()
        self._http_duration.labels(method=method, path=path).observe(duration_seconds)

    def render(self, *, session_factory: SessionFactory | None, include_database: bool) -> bytes:
        if include_database and session_factory is not None:
            self.refresh_database_metrics(session_factory)
        return generate_latest(self.registry)

    def refresh_database_metrics(self, session_factory: SessionFactory) -> ReadinessCheck:
        try:
            with session_scope(session_factory) as session:
                session.execute(text("SELECT 1"))
                self._db_readiness.set(1)
                self._open_sessions.set(
                    session.scalar(
                        select(func.count(BotSessionModel.id)).where(BotSessionModel.status == "running")
                    )
                    or 0
                )
                self._open_positions.set(
                    session.scalar(select(func.count(PositionModel.id)).where(PositionModel.status == "open")) or 0
                )
                self._unprotected_orders.set(
                    session.scalar(
                        select(func.count(OrderModel.id)).where(
                            (OrderModel.requires_manual_review.is_(True))
                            | (OrderModel.state == OrderLifecycleState.FAILED_UNPROTECTED)
                        )
                    )
                    or 0
                )
                for severity in ("INFO", "WARNING", "CRITICAL", "EMERGENCY"):
                    self._risk_events.labels(severity=severity).set(
                        session.scalar(select(func.count(RiskEventModel.id)).where(RiskEventModel.severity == severity))
                        or 0
                    )
                risk_state = session.scalar(select(RiskStateModel).order_by(RiskStateModel.id.asc()))
                self._risk_state.labels(flag="kill_switch_enabled").set(
                    1 if risk_state is not None and risk_state.kill_switch_enabled else 0
                )
                self._risk_state.labels(flag="manual_pause_enabled").set(
                    1 if risk_state is not None and risk_state.manual_pause_enabled else 0
                )
                self._risk_state.labels(flag="daily_loss_locked").set(
                    1 if risk_state is not None and risk_state.daily_loss_locked else 0
                )
                self._risk_state.labels(flag="drawdown_locked").set(
                    1 if risk_state is not None and risk_state.drawdown_locked else 0
                )
                self._set_record_count("signals", session.scalar(select(func.count(SignalModel.id))) or 0)
                self._set_record_count("orders", session.scalar(select(func.count(OrderModel.id))) or 0)
                self._set_record_count("positions", session.scalar(select(func.count(PositionModel.id))) or 0)
                self._set_record_count("trades", session.scalar(select(func.count(TradeModel.id))) or 0)
                self._set_record_count("risk_events", session.scalar(select(func.count(RiskEventModel.id))) or 0)
                self._set_record_count("backtest_runs", session.scalar(select(func.count(BacktestRunModel.id))) or 0)
                self._set_record_count("ai_reports", session.scalar(select(func.count(AIReportModel.id))) or 0)
                self._set_record_count("exchange_fills", session.scalar(select(func.count(ExchangeFillModel.id))) or 0)
        except SQLAlchemyError as exc:
            self._db_readiness.set(0)
            return ReadinessCheck(status="degraded", details={"database": str(exc)})
        return ReadinessCheck(status="ok", details={"database": "ok"})

    def _set_record_count(self, table: str, value: int) -> None:
        self._records.labels(table=table).set(value)


def check_database_readiness(session_factory: SessionFactory) -> ReadinessCheck:
    try:
        with session_scope(session_factory) as session:
            session.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        return ReadinessCheck(status="degraded", details={"database": str(exc)})
    return ReadinessCheck(status="ok", details={"database": "ok"})
