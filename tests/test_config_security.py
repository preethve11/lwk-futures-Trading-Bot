from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import load_settings
from app.core.security import assert_live_trading_allowed


def test_load_settings_reads_yaml_and_env_overrides(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
api:
  use_testnet: true
strategy:
  symbol: btcusdt
  timeframe: 15m
  ema_fast: 5
risk:
  risk_per_trade_usd: 25
execution:
  leverage: 3
logging:
  level: warning
backtest:
  start_date: "2026-01-01T00:00:00Z"
  end_date: "2026-01-02T00:00:00Z"
  initial_capital: 5000
monitoring:
  account_reconciliation_interval_seconds: 120
  account_equity_drift_threshold_usd: 15
  account_equity_drift_threshold_pct: 2.5
  live_strategy_gate_enabled: true
  live_gate_min_trades: 40
  live_gate_min_profit_factor: 1.2
  live_gate_max_drawdown_pct: 12
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("SYMBOL", "ethusdt")
    monkeypatch.setenv("LEVERAGE", "7")

    settings = load_settings(config_path=config_path, project_root=tmp_path)

    assert settings.symbol == "ETHUSDT"
    assert settings.timeframe == "15m"
    assert settings.ema_fast == 5
    assert settings.risk_per_trade_usd == 25
    assert settings.leverage == 7
    assert settings.log_level == "WARNING"
    assert settings.backtest_initial_capital == 5000
    assert settings.account_reconciliation_interval_seconds == 120
    assert settings.account_equity_drift_threshold_usd == 15
    assert settings.account_equity_drift_threshold_pct == 2.5
    assert settings.live_strategy_gate_enabled is True
    assert settings.live_gate_min_trades == 40
    assert settings.live_gate_min_profit_factor == 1.2
    assert settings.live_gate_max_drawdown_pct == 12


def test_active_binance_keys_follow_testnet_flag(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "test-key")
    monkeypatch.setenv("BINANCE_TESTNET_API_SECRET", "test-secret")
    monkeypatch.setenv("BINANCE_MAINNET_API_KEY", "main-key")
    monkeypatch.setenv("BINANCE_MAINNET_API_SECRET", "main-secret")

    testnet_settings = load_settings(project_root=tmp_path)
    mainnet_config = tmp_path / "mainnet.yaml"
    mainnet_config.write_text("api:\n  use_testnet: false\n", encoding="utf-8")
    mainnet_settings = load_settings(config_path=mainnet_config, project_root=tmp_path)

    assert testnet_settings.active_binance_api_key == "test-key"
    assert testnet_settings.active_binance_api_secret == "test-secret"
    assert mainnet_settings.active_binance_api_key == "main-key"
    assert mainnet_settings.active_binance_api_secret == "main-secret"


def test_live_guard_allows_testnet(tmp_path: Path) -> None:
    settings = load_settings(project_root=tmp_path)

    assert_live_trading_allowed(settings)


def test_live_guard_blocks_unconfirmed_mainnet(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("api:\n  use_testnet: false\n", encoding="utf-8")
    settings = load_settings(config_path=config_path, project_root=tmp_path)

    with pytest.raises(RuntimeError, match="Live trading blocked"):
        assert_live_trading_allowed(settings)


def test_live_guard_allows_confirmed_mainnet(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("api:\n  use_testnet: false\n", encoding="utf-8")
    monkeypatch.setenv("CONFIRM_LIVE_TRADING", "true")
    settings = load_settings(config_path=config_path, project_root=tmp_path)

    assert_live_trading_allowed(settings)
