from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config as AlembicConfig
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect

from app.api.main import create_app
from app.core.config import Settings


ROOT = Path(__file__).resolve().parents[1]


def _alembic_config(database_url: str) -> AlembicConfig:
    config = AlembicConfig(str(ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def test_alembic_upgrade_head_creates_current_schema(tmp_path: Path) -> None:
    database_path = tmp_path / "migration.db"
    database_url = f"sqlite:///{database_path}"

    command.upgrade(_alembic_config(database_url), "head")

    engine = create_engine(database_url, future=True)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    order_columns = {column["name"] for column in inspector.get_columns("orders")}
    trade_columns = {column["name"] for column in inspector.get_columns("trades")}
    exchange_fill_columns = {column["name"] for column in inspector.get_columns("exchange_fills")}

    assert "alembic_version" in tables
    assert {
        "bot_sessions",
        "configs",
        "risk_state",
        "signals",
        "orders",
        "positions",
        "trades",
        "risk_events",
        "backtest_runs",
        "ai_reports",
        "exchange_fills",
    }.issubset(tables)
    assert {
        "stop_order_id",
        "take_profit_order_id",
        "protected",
        "requires_manual_review",
        "emergency_close_order_id",
        "exchange_status",
        "filled_quantity",
        "remaining_quantity",
        "last_reconciled_at",
    }.issubset(order_columns)
    assert {
        "exchange_trade_id",
        "exchange_order_id",
    }.issubset(trade_columns)
    assert {
        "exchange_trade_id",
        "exchange_order_id",
        "realized_pnl",
        "commission",
        "raw_payload",
    }.issubset(exchange_fill_columns)


def test_api_startup_can_skip_auto_create_tables(tmp_path: Path) -> None:
    database_path = tmp_path / "no_create.db"
    settings = Settings(
        database_url=f"sqlite:///{database_path}",
        database_auto_create_tables=False,
        readiness_check_database=False,
    )

    client = TestClient(create_app(settings=settings, init_database=True))
    response = client.get("/health")

    engine = create_engine(settings.database_url, future=True)
    tables = inspect(engine).get_table_names()
    assert response.status_code == 200
    assert tables == []

