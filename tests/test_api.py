from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.api.main import create_app
from app.core.config import Settings
from app.persistence.database import SessionFactory, create_session_factory, init_db, session_scope
from app.persistence.models import PositionModel
from app.persistence.repositories import BotSessionRepository, RiskEventRepository, SignalRepository, TradeRepository
from trading_bot.analytics.metrics import PerformanceMetrics
from trading_bot.core.types import Signal, SignalSide, Trade


def _client() -> tuple[TestClient, SessionFactory]:
    settings = Settings(api_token="secret", database_url="sqlite:///:memory:")
    factory = create_session_factory(settings.database_url)
    init_db(factory)
    return TestClient(create_app(settings=settings, session_factory=factory, init_database=False)), factory


def _headers() -> dict[str, str]:
    return {"X-API-Token": "secret"}


def _seed_data(factory: SessionFactory) -> None:
    with session_scope(factory) as session:
        bot_session = BotSessionRepository(session).create(
            mode="paper",
            strategy_name="ema_rsi_vwap",
            symbol="ZECUSDT",
            timeframe="5m",
        )
        signal = SignalRepository(session).create_from_signal(
            Signal(
                side=SignalSide.LONG,
                entry_price=100.0,
                stop_price=99.0,
                take_profit_price=102.0,
                quantity=0.5,
                timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            ),
            symbol="ZECUSDT",
            strategy_name="ema_rsi_vwap",
            bot_session_id=bot_session.id,
        )
        TradeRepository(session).create_from_trade(
            Trade(
                symbol="ZECUSDT",
                side=SignalSide.LONG,
                quantity=0.5,
                entry_price=100.0,
                exit_price=102.0,
                pnl=1.0,
                pnl_pct=2.0,
                entry_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
                exit_time=datetime(2026, 1, 1, 1, tzinfo=timezone.utc),
                exit_reason="take_profit",
            ),
            bot_session_id=bot_session.id,
            signal_id=signal.id,
            source="backtest",
        )
        TradeRepository(session).create_backtest_run(
            strategy_name="ema_rsi_vwap",
            symbol="ZECUSDT",
            timeframe="5m",
            initial_capital=10_000.0,
            final_capital=10_001.0,
            metrics=PerformanceMetrics(
                total_return_pct=0.01,
                sharpe_ratio=0.0,
                sortino_ratio=0.0,
                max_drawdown_pct=0.0,
                win_rate=1.0,
                profit_factor=float("inf"),
                expectancy=1.0,
                total_trades=1,
                winning_trades=1,
                losing_trades=0,
                avg_win=1.0,
                avg_loss=0.0,
            ),
        )
        session.add(
            PositionModel(
                bot_session_id=bot_session.id,
                symbol="ZECUSDT",
                side="BUY",
                quantity=0.5,
                entry_price=100.0,
                unrealized_pnl=2.0,
                leverage=5,
                status="open",
                opened_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )
        )
        RiskEventRepository(session).create(
            bot_session_id=bot_session.id,
            symbol="ZECUSDT",
            event_type="manual_review_required",
            severity="CRITICAL",
            reason="test",
        )


def test_api_rejects_invalid_token() -> None:
    client, _ = _client()

    response = client.get("/trades", headers={"X-API-Token": "wrong"})

    assert response.status_code == 401


def test_api_allows_configured_frontend_origin() -> None:
    client, _ = _client()

    response = client.options(
        "/trades",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "X-API-Token",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"


def test_configs_create_and_list() -> None:
    client, _ = _client()

    created = client.post(
        "/configs",
        headers=_headers(),
        json={"name": "testnet", "payload": {"symbol": "ZECUSDT"}, "is_active": True},
    )
    listed = client.get("/configs", headers=_headers())

    assert created.status_code == 200
    assert created.json()["is_active"] is True
    assert listed.status_code == 200
    assert listed.json()[0]["name"] == "testnet"


def test_repository_backed_read_endpoints() -> None:
    client, factory = _client()
    _seed_data(factory)

    trades = client.get("/trades", headers=_headers())
    trade = client.get("/trades/1", headers=_headers())
    signals = client.get("/signals", headers=_headers())
    sessions = client.get("/sessions", headers=_headers())
    backtests = client.get("/backtests", headers=_headers())
    positions = client.get("/positions", headers=_headers())
    risk_events = client.get("/risk/events", headers=_headers())

    assert trades.status_code == 200
    assert trades.json()[0]["symbol"] == "ZECUSDT"
    assert trade.status_code == 200
    assert trade.json()["pnl"] == 1.0
    assert signals.status_code == 200
    assert signals.json()[0]["side"] == "BUY"
    assert sessions.status_code == 200
    assert sessions.json()[0]["mode"] == "paper"
    assert backtests.status_code == 200
    assert backtests.json()[0]["total_trades"] == 1
    assert positions.status_code == 200
    assert positions.json()[0]["status"] == "open"
    assert risk_events.status_code == 200
    assert risk_events.json()[0]["severity"] == "CRITICAL"


def test_sessions_start_stop_and_risk_kill_switch() -> None:
    client, _ = _client()

    started = client.post("/sessions/start", headers=_headers(), json={"mode": "paper"})
    session_id = started.json()["id"]
    stopped = client.post("/sessions/stop", headers=_headers(), json={"session_id": session_id})
    risk_state = client.post(
        "/risk/kill-switch",
        headers=_headers(),
        json={"enabled": True, "reason": "operator requested"},
    )
    updated_state = client.post(
        "/risk/state",
        headers=_headers(),
        json={"manual_pause_enabled": True, "daily_loss_locked": True, "reason": "dashboard"},
    )

    assert started.status_code == 200
    assert stopped.status_code == 200
    assert stopped.json()["status"] == "stopped"
    assert risk_state.status_code == 200
    assert risk_state.json()["kill_switch_enabled"] is True
    assert updated_state.status_code == 200
    assert updated_state.json()["manual_pause_enabled"] is True
    assert updated_state.json()["daily_loss_locked"] is True


def test_websocket_receives_live_events() -> None:
    client, _ = _client()

    with client.websocket_connect("/ws/live") as websocket:
        assert websocket.receive_json()["event_type"] == "connected"
        response = client.post(
            "/risk/kill-switch",
            headers=_headers(),
            json={"enabled": True, "reason": "test"},
        )
        assert response.status_code == 200
        event = websocket.receive_json()

    assert event["event_type"] == "risk_event"
    assert event["payload"]["kill_switch_enabled"] is True


def test_backtest_run_endpoint_persists_result() -> None:
    client, _ = _client()
    candles = [
        {
            "time": f"2026-01-01T00:{minute:02d}:00Z",
            "open": 100 + minute,
            "high": 103 + minute,
            "low": 99 + minute,
            "close": 100 + minute,
            "volume": 1000,
        }
        for minute in range(30)
    ]

    response = client.post(
        "/backtests/run",
        headers=_headers(),
        json={"symbol": "ZECUSDT", "timeframe": "5m", "candles": candles},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["backtest_run"]["symbol"] == "ZECUSDT"
    assert body["equity_curve"]


def test_multi_symbol_backtest_run_endpoint_persists_aggregate() -> None:
    client, _ = _client()
    candles = [
        {
            "time": f"2026-01-01T00:{minute:02d}:00Z",
            "open": 100 + minute,
            "high": 103 + minute,
            "low": 99 + minute,
            "close": 100 + minute,
            "volume": 1000,
        }
        for minute in range(36)
    ]

    response = client.post(
        "/backtests/run-multi",
        headers=_headers(),
        json={
            "symbols": ["ZECUSDT", "BTCUSDT"],
            "timeframe": "5m",
            "candles_by_symbol": {
                "ZECUSDT": candles,
                "BTCUSDT": candles,
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["aggregate"]["symbol"] == "MULTI"
    assert len(body["symbols"]) == 2
    assert {symbol["symbol"] for symbol in body["symbols"]} == {"ZECUSDT", "BTCUSDT"}
