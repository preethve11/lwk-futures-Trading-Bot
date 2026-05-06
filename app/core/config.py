"""Typed application settings loaded from YAML, environment, and .env."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import yaml  # type: ignore[import-untyped]
from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated settings for the trading platform.

    Secrets are read from environment variables or a local .env file. Public
    strategy/risk defaults mirror the existing config.yaml so the new platform
    can be introduced without changing current trading behavior.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: Literal["local", "staging", "production"] = "local"
    use_testnet: bool = True
    confirm_live_trading: bool = False

    binance_api_key: str = ""
    binance_api_secret: str = ""
    binance_testnet_api_key: str = ""
    binance_testnet_api_secret: str = ""
    binance_mainnet_api_key: str = ""
    binance_mainnet_api_secret: str = ""

    strategy_name: str = "ema_rsi_vwap"
    symbol: str = "ZECUSDT"
    symbols: list[str] = Field(default_factory=lambda: ["ZECUSDT"])
    timeframe: str = "5m"

    ema_fast: int = Field(default=9, gt=0)
    ema_slow: int = Field(default=21, gt=0)
    rsi_len: int = Field(default=7, gt=0)
    atr_len: int = Field(default=14, gt=0)
    atr_stop_mult: float = Field(default=0.8, gt=0)
    atr_tp_mult: float = Field(default=1.6, gt=0)
    vol_mult: float = Field(default=1.5, gt=0)
    vol_ma_len: int = Field(default=20, gt=0)
    rsi_long_min: float = Field(default=48.0, ge=0, le=100)
    rsi_short_max: float = Field(default=52.0, ge=0, le=100)
    cooldown_candles: int = Field(default=1, ge=0)

    risk_per_trade_usd: float = Field(default=10.0, gt=0)
    max_daily_loss_usd: float = Field(default=50.0, gt=0)
    max_drawdown_pct: float = Field(default=20.0, gt=0, le=100)
    min_notional: float = Field(default=5.0, gt=0)
    max_position_pct_capital: float = Field(default=100.0, gt=0)
    use_atr_position_cap: bool = True
    trailing_stop_atr_mult: float = Field(default=0.0, ge=0)
    min_risk_reward: float = Field(default=1.0, gt=0)

    leverage: int = Field(default=5, gt=0)
    slippage_bps: float = Field(default=5.0, ge=0)
    fee_bps: float = Field(default=4.0, ge=0)

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    log_level: str = "INFO"
    log_dir: Path = Path("logs")
    log_file: str = "trading_bot.log"

    backtest_start: str | None = None
    backtest_end: str | None = None
    backtest_initial_capital: float = Field(default=10000.0, gt=0)
    historical_data_csv: Path | None = None
    historical_data_dir: Path | None = None
    backtest_report_dir: Path = Path("reports/backtests")

    database_url: str = "sqlite:///./trading_bot.db"
    redis_url: str = "redis://localhost:6379/0"
    market_data_source: Literal["rest", "redis"] = "rest"
    market_data_channel: str = "market_data.kline"
    market_data_history_size: int = Field(default=500, gt=0)
    market_data_reconnect_backoff_seconds: float = Field(default=2.0, gt=0)
    api_token: str = ""
    api_cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://127.0.0.1:5173",
            "http://localhost:5173",
            "http://127.0.0.1:8080",
            "http://localhost:8080",
        ]
    )
    openai_api_key: str = ""

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("symbols", mode="before")
    @classmethod
    def normalize_symbols(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [item.strip().upper() for item in value.split(",") if item.strip()]
        return [item.strip().upper() for item in value]

    @field_validator("api_cors_origins", mode="before")
    @classmethod
    def normalize_cors_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return [item.strip() for item in value]

    @field_validator("log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        return value.strip().upper()

    @property
    def active_binance_api_key(self) -> str:
        if self.use_testnet:
            return self.binance_testnet_api_key or self.binance_api_key
        return self.binance_mainnet_api_key or self.binance_api_key

    @property
    def active_binance_api_secret(self) -> str:
        if self.use_testnet:
            return self.binance_testnet_api_secret or self.binance_api_secret
        return self.binance_mainnet_api_secret or self.binance_api_secret


def get_settings() -> Settings:
    """Create settings from environment for application entrypoints."""
    return Settings()


def load_settings(config_path: Path | None = None, project_root: Path | None = None) -> Settings:
    """Load settings from config.yaml, then let explicit environment values win."""
    root = project_root or Path.cwd()
    env_path = root / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=False)

    yaml_values = _load_yaml_values(config_path or root / "config.yaml")
    init_values = {
        field_name: value
        for field_name, value in yaml_values.items()
        if not _env_present(field_name)
    }
    return Settings(**init_values)


def _env_present(field_name: str) -> bool:
    """Return True when the standard env var for a settings field is present."""
    return field_name.upper() in os.environ


def _load_yaml_values(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}

    with open(path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    api = data.get("api", {})
    strategy = data.get("strategy", {})
    risk = data.get("risk", {})
    execution = data.get("execution", {})
    telegram = data.get("telegram", {})
    logging_config = data.get("logging", {})
    backtest = data.get("backtest", {})
    market_data = data.get("market_data", {})

    values: dict[str, Any] = {
        "use_testnet": api.get("use_testnet"),
        "strategy_name": strategy.get("name") or strategy.get("strategy_name"),
        "symbol": strategy.get("symbol"),
        "symbols": strategy.get("symbols"),
        "timeframe": strategy.get("timeframe"),
        "ema_fast": strategy.get("ema_fast"),
        "ema_slow": strategy.get("ema_slow"),
        "rsi_len": strategy.get("rsi_len"),
        "atr_len": strategy.get("atr_len"),
        "atr_stop_mult": strategy.get("atr_stop_mult"),
        "atr_tp_mult": strategy.get("atr_tp_mult"),
        "vol_mult": strategy.get("vol_mult"),
        "vol_ma_len": strategy.get("vol_ma_len"),
        "rsi_long_min": strategy.get("rsi_long_min"),
        "rsi_short_max": strategy.get("rsi_short_max"),
        "cooldown_candles": strategy.get("cooldown_candles"),
        "risk_per_trade_usd": risk.get("risk_per_trade_usd"),
        "max_daily_loss_usd": risk.get("max_daily_loss_usd"),
        "max_drawdown_pct": risk.get("max_drawdown_pct"),
        "min_notional": risk.get("min_notional"),
        "max_position_pct_capital": risk.get("max_position_pct_capital"),
        "use_atr_position_cap": risk.get("use_atr_position_cap"),
        "trailing_stop_atr_mult": risk.get("trailing_stop_atr_mult"),
        "min_risk_reward": risk.get("min_risk_reward"),
        "leverage": execution.get("leverage"),
        "slippage_bps": execution.get("slippage_bps"),
        "fee_bps": execution.get("fee_bps"),
        "telegram_bot_token": telegram.get("bot_token"),
        "telegram_chat_id": telegram.get("chat_id"),
        "log_level": logging_config.get("level"),
        "log_dir": logging_config.get("log_dir"),
        "log_file": logging_config.get("log_file"),
        "backtest_start": backtest.get("start_date"),
        "backtest_end": backtest.get("end_date"),
        "backtest_initial_capital": backtest.get("initial_capital"),
        "historical_data_csv": backtest.get("historical_data_csv"),
        "historical_data_dir": backtest.get("historical_data_dir"),
        "backtest_report_dir": backtest.get("report_dir"),
        "market_data_source": market_data.get("source"),
        "market_data_channel": market_data.get("channel"),
        "market_data_history_size": market_data.get("history_size"),
        "market_data_reconnect_backoff_seconds": market_data.get("reconnect_backoff_seconds"),
    }
    return {key: value for key, value in values.items() if value is not None}
