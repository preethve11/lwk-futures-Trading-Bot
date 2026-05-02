"""Typed application settings loaded from environment and .env."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, computed_field, field_validator
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

    database_url: str = "sqlite:///./trading_bot.db"
    redis_url: str = "redis://localhost:6379/0"
    api_token: str = ""
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

    @field_validator("log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        return value.strip().upper()

    @computed_field
    @property
    def active_binance_api_key(self) -> str:
        if self.use_testnet:
            return self.binance_testnet_api_key or self.binance_api_key
        return self.binance_mainnet_api_key or self.binance_api_key

    @computed_field
    @property
    def active_binance_api_secret(self) -> str:
        if self.use_testnet:
            return self.binance_testnet_api_secret or self.binance_api_secret
        return self.binance_mainnet_api_secret or self.binance_api_secret


def get_settings() -> Settings:
    """Create settings from environment for application entrypoints."""
    return Settings()
