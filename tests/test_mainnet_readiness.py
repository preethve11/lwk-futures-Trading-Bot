from __future__ import annotations

from app.core.config import Settings
from app.ops.mainnet_readiness import ReadinessStatus, evaluate_mainnet_readiness


def test_mainnet_readiness_fails_closed_for_default_testnet_config() -> None:
    report = evaluate_mainnet_readiness(Settings(), small_notional_usd=10)

    failures = {check.name for check in report.failed}

    assert report.ready is False
    assert "Mainnet mode" in failures
    assert "Live trading confirmation" in failures
    assert "Mainnet API credentials" in failures
    assert "API token" in failures


def test_mainnet_readiness_accepts_small_notional_production_like_config() -> None:
    report = evaluate_mainnet_readiness(
        Settings(
            use_testnet=False,
            enable_live_trading=True,
            confirm_live_trading=True,
            binance_mainnet_api_key="main-key",
            binance_mainnet_api_secret="main-secret",
            api_token="operator-token",
            database_url="postgresql+psycopg://trading_bot:trading_bot@postgres:5432/trading_bot",
            database_auto_create_tables=False,
            risk_per_trade_usd=5,
            max_daily_loss_usd=10,
            max_drawdown_pct=10,
            telegram_bot_token="telegram-token",
            telegram_chat_id="chat-id",
            account_reconciliation_interval_seconds=120,
            account_equity_drift_threshold_usd=5,
            market_data_source="redis",
        ),
        small_notional_usd=10,
    )

    assert report.ready is True
    assert {check.status for check in report.checks} == {ReadinessStatus.PASS}


def test_mainnet_readiness_flags_oversized_risk_controls() -> None:
    report = evaluate_mainnet_readiness(
        Settings(
            use_testnet=False,
            enable_live_trading=True,
            confirm_live_trading=True,
            binance_mainnet_api_key="main-key",
            binance_mainnet_api_secret="main-secret",
            api_token="operator-token",
            risk_per_trade_usd=25,
            max_daily_loss_usd=100,
        ),
        small_notional_usd=10,
    )

    failures = {check.name for check in report.failed}

    assert "Small-notional risk" in failures
    assert "Daily loss cap" in failures
