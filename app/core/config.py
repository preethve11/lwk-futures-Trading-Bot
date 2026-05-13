"""Typed application settings loaded from YAML, environment, and .env."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import yaml
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
    enable_live_trading: bool = False
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
    vwap_window: int = Field(default=0, ge=0)
    rsi_long_min: float = Field(default=48.0, ge=0, le=100)
    rsi_short_max: float = Field(default=52.0, ge=0, le=100)
    cooldown_candles: int = Field(default=1, ge=0)
    session_breakout_sessions: list[str] = Field(
        default_factory=lambda: ["nse:03:45", "london:08:00", "new_york:14:30"]
    )
    session_breakout_pre_open_minutes: int = Field(default=120, gt=0)
    session_breakout_trade_window_minutes: int = Field(default=240, gt=0)
    session_breakout_min_range_width_pct: float = Field(default=0.4, ge=0)
    session_breakout_ema_length: int = Field(default=50, gt=0)
    session_breakout_adx_length: int = Field(default=14, gt=0)
    session_breakout_min_adx: float = Field(default=20.0, ge=0)
    session_breakout_entry_buffer_pct: float = Field(default=0.0, ge=0)
    session_breakout_enabled_timeframes: list[str] = Field(default_factory=lambda: ["15m", "1h"])
    adaptive_momentum_symbols: list[str] = Field(
        default_factory=lambda: ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "LINKUSDT"]
    )
    adaptive_momentum_research_only_symbols: list[str] = Field(default_factory=lambda: ["ZECUSDT"])
    adaptive_momentum_enabled_timeframes: list[str] = Field(default_factory=lambda: ["15m", "1h"])
    adaptive_momentum_donchian_window: int = Field(default=20, gt=0)
    adaptive_momentum_ema_fast: int = Field(default=50, gt=0)
    adaptive_momentum_ema_slow: int = Field(default=200, gt=0)
    adaptive_momentum_adx_length: int = Field(default=14, gt=0)
    adaptive_momentum_long_adx_min: float = Field(default=22.0, ge=0)
    adaptive_momentum_short_adx_min: float = Field(default=25.0, ge=0)
    adaptive_momentum_volume_ratio_min: float = Field(default=1.1, ge=0)
    adaptive_momentum_atr_length: int = Field(default=14, gt=0)
    adaptive_momentum_stop_atr_mult: float = Field(default=2.5, gt=0)
    adaptive_momentum_take_profit_r_multiple: float = Field(default=2.0, gt=0)
    adaptive_momentum_trailing_stop_atr_mult: float = Field(default=3.0, ge=0)
    adaptive_momentum_max_holding_bars: int = Field(default=120, gt=0)
    adaptive_momentum_spread_max_bps: float = Field(default=8.0, gt=0)
    adaptive_momentum_funding_rate_abs_long_max: float = Field(default=0.0003, ge=0)
    adaptive_momentum_funding_rate_abs_short_max: float = Field(default=0.0003, ge=0)
    adaptive_momentum_funding_rate_delta_max: float = Field(default=0.0001, ge=0)
    adaptive_momentum_open_interest_spike_pct_max: float = Field(default=12.0, ge=0)
    adaptive_momentum_adl_quantile_max: float = Field(default=3.0, ge=0)
    adaptive_momentum_liquidation_spike_ratio_max: float = Field(default=3.0, ge=0)
    adaptive_momentum_volatility_shock_percentile_min: float = Field(default=0.9, ge=0, le=1)
    adaptive_momentum_allowed_days_of_week: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4, 5, 6])
    adaptive_momentum_blocked_hours_utc: list[int] = Field(default_factory=list)
    adaptive_momentum_max_expected_cost_share: float = Field(default=0.35, gt=0, le=1)
    adaptive_momentum_short_position_size_multiplier: float = Field(default=0.5, gt=0, le=1)

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
    walk_forward_train_size: int = Field(default=500, gt=0)
    walk_forward_validation_size: int = Field(default=100, gt=0)
    walk_forward_step_size: int = Field(default=100, gt=0)
    walk_forward_embargo_size: int = Field(default=0, ge=0)
    walk_forward_trials: int = Field(default=30, gt=0)
    walk_forward_objective: Literal["sharpe", "sortino", "total_return", "profit_factor", "win_rate"] = "sharpe"
    walk_forward_random_seed: int = 42
    walk_forward_report_dir: Path = Path("reports/optimizations")
    monte_carlo_simulations: int = Field(default=1000, gt=0)
    monte_carlo_horizon_trades: int = Field(default=100, gt=0)
    monte_carlo_ruin_drawdown_pct: float = Field(default=30.0, ge=0, le=100)
    monte_carlo_random_seed: int = 42
    monte_carlo_report_dir: Path = Path("reports/monte_carlo")

    database_url: str = "sqlite:///./trading_bot.db"
    database_auto_create_tables: bool = True
    redis_url: str = "redis://localhost:6379/0"
    market_data_source: Literal["rest", "redis"] = "rest"
    market_data_symbols: list[str] = Field(default_factory=lambda: ["BTCUSDT", "ETHUSDT", "SOLUSDT"])
    market_data_timeframes: list[str] = Field(default_factory=lambda: ["5m", "15m", "1h"])
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
    openai_base_url: str = "https://api.openai.com/v1"
    ai_journal_enabled: bool = False
    ai_journal_model: str = "gpt-4.1-mini"
    ai_journal_timeout_seconds: float = Field(default=15.0, gt=0)
    ai_journal_max_queue_size: int = Field(default=1000, gt=0)
    metrics_enabled: bool = True
    metrics_include_database: bool = True
    metrics_token: str = ""
    readiness_check_database: bool = True
    account_reconciliation_interval_seconds: int = Field(default=300, gt=0)
    account_equity_drift_threshold_usd: float = Field(default=25.0, ge=0)
    account_equity_drift_threshold_pct: float = Field(default=5.0, ge=0)
    live_strategy_gate_enabled: bool = False
    live_strategy_gate_required_for_mainnet: bool = True
    live_gate_min_trades: int = Field(default=100, ge=0)
    live_gate_min_profit_factor: float = Field(default=1.25, ge=0)
    live_gate_min_expectancy_usd: float = Field(default=0.0)
    live_gate_min_sharpe: float = Field(default=0.0)
    live_gate_max_drawdown_pct: float = Field(default=15.0, gt=0, le=100)
    live_gate_max_backtest_age_days: int = Field(default=30, gt=0)

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

    @field_validator(
        "session_breakout_sessions",
        "session_breakout_enabled_timeframes",
        "adaptive_momentum_symbols",
        "adaptive_momentum_research_only_symbols",
        "adaptive_momentum_enabled_timeframes",
        "market_data_symbols",
        "market_data_timeframes",
        mode="before",
    )
    @classmethod
    def normalize_string_list(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return [item.strip() for item in value]

    @field_validator("adaptive_momentum_allowed_days_of_week", "adaptive_momentum_blocked_hours_utc", mode="before")
    @classmethod
    def normalize_int_list(cls, value: str | list[int]) -> list[int]:
        if isinstance(value, str):
            return [int(item.strip()) for item in value.split(",") if item.strip()]
        return [int(item) for item in value]

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
    adaptive_momentum = strategy.get("adaptive_momentum_breakout", {})
    risk = data.get("risk", {})
    execution = data.get("execution", {})
    telegram = data.get("telegram", {})
    logging_config = data.get("logging", {})
    backtest = data.get("backtest", {})
    optimization = data.get("optimization", {})
    walk_forward = optimization.get("walk_forward", {})
    monte_carlo = optimization.get("monte_carlo", {})
    market_data = data.get("market_data", {})
    persistence = data.get("persistence", {})
    ai_journal = data.get("ai_journal", {})
    monitoring = data.get("monitoring", {})

    values: dict[str, Any] = {
        "use_testnet": api.get("use_testnet"),
        "enable_live_trading": api.get("enable_live_trading"),
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
        "vwap_window": strategy.get("vwap_window"),
        "rsi_long_min": strategy.get("rsi_long_min"),
        "rsi_short_max": strategy.get("rsi_short_max"),
        "cooldown_candles": strategy.get("cooldown_candles"),
        "session_breakout_sessions": strategy.get("session_breakout_sessions"),
        "session_breakout_pre_open_minutes": strategy.get("session_breakout_pre_open_minutes"),
        "session_breakout_trade_window_minutes": strategy.get("session_breakout_trade_window_minutes"),
        "session_breakout_min_range_width_pct": strategy.get("session_breakout_min_range_width_pct"),
        "session_breakout_ema_length": strategy.get("session_breakout_ema_length"),
        "session_breakout_adx_length": strategy.get("session_breakout_adx_length"),
        "session_breakout_min_adx": strategy.get("session_breakout_min_adx"),
        "session_breakout_entry_buffer_pct": strategy.get("session_breakout_entry_buffer_pct"),
        "session_breakout_enabled_timeframes": strategy.get("session_breakout_enabled_timeframes"),
        "adaptive_momentum_symbols": adaptive_momentum.get("symbols"),
        "adaptive_momentum_research_only_symbols": adaptive_momentum.get("research_only_symbols"),
        "adaptive_momentum_enabled_timeframes": adaptive_momentum.get("enabled_timeframes"),
        "adaptive_momentum_donchian_window": adaptive_momentum.get("donchian_window"),
        "adaptive_momentum_ema_fast": adaptive_momentum.get("ema_fast"),
        "adaptive_momentum_ema_slow": adaptive_momentum.get("ema_slow"),
        "adaptive_momentum_adx_length": adaptive_momentum.get("adx_length"),
        "adaptive_momentum_long_adx_min": adaptive_momentum.get("long_adx_min"),
        "adaptive_momentum_short_adx_min": adaptive_momentum.get("short_adx_min"),
        "adaptive_momentum_volume_ratio_min": adaptive_momentum.get("volume_ratio_min"),
        "adaptive_momentum_atr_length": adaptive_momentum.get("atr_length"),
        "adaptive_momentum_stop_atr_mult": adaptive_momentum.get("stop_atr_mult"),
        "adaptive_momentum_take_profit_r_multiple": adaptive_momentum.get("take_profit_r_multiple"),
        "adaptive_momentum_trailing_stop_atr_mult": adaptive_momentum.get("trailing_stop_atr_mult"),
        "adaptive_momentum_max_holding_bars": adaptive_momentum.get("max_holding_bars"),
        "adaptive_momentum_spread_max_bps": adaptive_momentum.get("spread_max_bps"),
        "adaptive_momentum_funding_rate_abs_long_max": adaptive_momentum.get("funding_rate_abs_long_max"),
        "adaptive_momentum_funding_rate_abs_short_max": adaptive_momentum.get("funding_rate_abs_short_max"),
        "adaptive_momentum_funding_rate_delta_max": adaptive_momentum.get("funding_rate_delta_max"),
        "adaptive_momentum_open_interest_spike_pct_max": adaptive_momentum.get("open_interest_spike_pct_max"),
        "adaptive_momentum_adl_quantile_max": adaptive_momentum.get("adl_quantile_max"),
        "adaptive_momentum_liquidation_spike_ratio_max": adaptive_momentum.get("liquidation_spike_ratio_max"),
        "adaptive_momentum_volatility_shock_percentile_min": adaptive_momentum.get("volatility_shock_percentile_min"),
        "adaptive_momentum_allowed_days_of_week": adaptive_momentum.get("allowed_days_of_week"),
        "adaptive_momentum_blocked_hours_utc": adaptive_momentum.get("blocked_hours_utc"),
        "adaptive_momentum_max_expected_cost_share": adaptive_momentum.get("max_expected_cost_share"),
        "adaptive_momentum_short_position_size_multiplier": adaptive_momentum.get("short_position_size_multiplier"),
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
        "walk_forward_train_size": walk_forward.get("train_size"),
        "walk_forward_validation_size": walk_forward.get("validation_size"),
        "walk_forward_step_size": walk_forward.get("step_size"),
        "walk_forward_embargo_size": walk_forward.get("embargo_size"),
        "walk_forward_trials": walk_forward.get("trials"),
        "walk_forward_objective": walk_forward.get("objective"),
        "walk_forward_random_seed": walk_forward.get("random_seed"),
        "walk_forward_report_dir": walk_forward.get("report_dir"),
        "monte_carlo_simulations": monte_carlo.get("simulations"),
        "monte_carlo_horizon_trades": monte_carlo.get("horizon_trades"),
        "monte_carlo_ruin_drawdown_pct": monte_carlo.get("ruin_drawdown_pct"),
        "monte_carlo_random_seed": monte_carlo.get("random_seed"),
        "monte_carlo_report_dir": monte_carlo.get("report_dir"),
        "database_auto_create_tables": persistence.get("auto_create_tables"),
        "market_data_source": market_data.get("source"),
        "market_data_symbols": market_data.get("symbols"),
        "market_data_timeframes": market_data.get("timeframes"),
        "market_data_channel": market_data.get("channel"),
        "market_data_history_size": market_data.get("history_size"),
        "market_data_reconnect_backoff_seconds": market_data.get("reconnect_backoff_seconds"),
        "ai_journal_enabled": ai_journal.get("enabled"),
        "ai_journal_model": ai_journal.get("model"),
        "ai_journal_timeout_seconds": ai_journal.get("timeout_seconds"),
        "ai_journal_max_queue_size": ai_journal.get("max_queue_size"),
        "metrics_enabled": monitoring.get("metrics_enabled"),
        "metrics_include_database": monitoring.get("metrics_include_database"),
        "metrics_token": monitoring.get("metrics_token"),
        "readiness_check_database": monitoring.get("readiness_check_database"),
        "account_reconciliation_interval_seconds": monitoring.get("account_reconciliation_interval_seconds"),
        "account_equity_drift_threshold_usd": monitoring.get("account_equity_drift_threshold_usd"),
        "account_equity_drift_threshold_pct": monitoring.get("account_equity_drift_threshold_pct"),
        "live_strategy_gate_enabled": monitoring.get("live_strategy_gate_enabled"),
        "live_strategy_gate_required_for_mainnet": monitoring.get("live_strategy_gate_required_for_mainnet"),
        "live_gate_min_trades": monitoring.get("live_gate_min_trades"),
        "live_gate_min_profit_factor": monitoring.get("live_gate_min_profit_factor"),
        "live_gate_min_expectancy_usd": monitoring.get("live_gate_min_expectancy_usd"),
        "live_gate_min_sharpe": monitoring.get("live_gate_min_sharpe"),
        "live_gate_max_drawdown_pct": monitoring.get("live_gate_max_drawdown_pct"),
        "live_gate_max_backtest_age_days": monitoring.get("live_gate_max_backtest_age_days"),
    }
    return {key: value for key, value in values.items() if value is not None}
