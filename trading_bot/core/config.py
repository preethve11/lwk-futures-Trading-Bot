"""
Load configuration from config.yaml and .env. API keys only from env.
"""

from __future__ import annotations
import os
from pathlib import Path
from typing import Any, Optional

import yaml
from dotenv import load_dotenv


def _env_path(project_root: Optional[Path] = None) -> Path:
    root = project_root or Path(__file__).resolve().parents[2]
    return root / ".env"


def load_dotenv_if_exists(project_root: Optional[Path] = None) -> None:
    """Load .env from project root if present."""
    path = _env_path(project_root)
    if path.exists():
        load_dotenv(path)


def load_config(config_path: Optional[Path] = None, project_root: Optional[Path] = None) -> "Config":
    """Load config.yaml and overlay with env. Returns Config dataclass."""
    load_dotenv_if_exists(project_root)
    root = project_root or Path(__file__).resolve().parents[2]
    path = config_path or root / "config.yaml"
    data: dict[str, Any] = {}
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

    # Env overrides (for secrets and overrides)
    def env(key: str, default: str = "") -> str:
        return os.getenv(key, default).strip()

    def env_bool(key: str, default: bool = False) -> bool:
        return os.getenv(key, str(default)).lower() in ("true", "1", "yes")

    def env_int(key: str, default: int = 0) -> int:
        try:
            return int(os.getenv(key, str(default)))
        except ValueError:
            return default

    def env_float(key: str, default: float = 0.0) -> float:
        try:
            return float(os.getenv(key, str(default)))
        except ValueError:
            return default

    api = data.get("api", {})
    strategy = data.get("strategy", {})
    risk = data.get("risk", {})
    execution = data.get("execution", {})
    telegram = data.get("telegram", {})

    use_testnet = env_bool("USE_TESTNET", api.get("use_testnet", True))
    # Prefer dedicated testnet/mainnet keys so you can keep both in .env and switch with USE_TESTNET
    if use_testnet:
        binance_api_key = env("BINANCE_TESTNET_API_KEY") or env("BINANCE_API_KEY", api.get("binance_api_key", ""))
        binance_api_secret = env("BINANCE_TESTNET_API_SECRET") or env("BINANCE_API_SECRET", api.get("binance_api_secret", ""))
    else:
        binance_api_key = env("BINANCE_MAINNET_API_KEY") or env("BINANCE_API_KEY", api.get("binance_api_key", ""))
        binance_api_secret = env("BINANCE_MAINNET_API_SECRET") or env("BINANCE_API_SECRET", api.get("binance_api_secret", ""))

    return Config(
        # API (env only; never put keys in config.yaml for GitHub safety)
        binance_api_key=binance_api_key,
        binance_api_secret=binance_api_secret,
        use_testnet=use_testnet,
        symbol=env("SYMBOL", strategy.get("symbol", "ZECUSDT")).upper(),
        timeframe=env("TIMEFRAME", strategy.get("timeframe", "5m")),
        leverage=env_int("LEVERAGE", execution.get("leverage", 5)),
        # Strategy
        ema_fast=env_int("EMA_FAST", strategy.get("ema_fast", 9)),
        ema_slow=env_int("EMA_SLOW", strategy.get("ema_slow", 21)),
        rsi_len=env_int("RSI_LEN", strategy.get("rsi_len", 7)),
        atr_len=env_int("ATR_LEN", strategy.get("atr_len", 14)),
        atr_stop_mult=env_float("ATR_STOP_MULT", strategy.get("atr_stop_mult", 0.8)),
        atr_tp_mult=env_float("ATR_TP_MULT", strategy.get("atr_tp_mult", 1.6)),
        vol_mult=env_float("VOL_MULT", strategy.get("vol_mult", 1.5)),
        vol_ma_len=env_int("VOL_MA_LEN", strategy.get("vol_ma_len", 20)),
        rsi_long_min=env_float("RSI_LONG_MIN", strategy.get("rsi_long_min", 48)),
        rsi_short_max=env_float("RSI_SHORT_MAX", strategy.get("rsi_short_max", 52)),
        cooldown_candles=env_int("COOLDOWN_CANDLES", strategy.get("cooldown_candles", 1)),
        # Risk
        risk_per_trade_usd=env_float("RISK_PER_TRADE_USD", risk.get("risk_per_trade_usd", 10.0)),
        max_daily_loss_usd=env_float("MAX_DAILY_LOSS_USD", risk.get("max_daily_loss_usd", 50.0)),
        max_drawdown_pct=env_float("MAX_DRAWDOWN_PCT", risk.get("max_drawdown_pct", 20.0)),
        min_notional=env_float("MIN_NOTIONAL", risk.get("min_notional", 5.0)),
        max_position_pct_capital=env_float("MAX_POSITION_PCT_CAPITAL", risk.get("max_position_pct_capital", 100.0)),
        use_atr_position_cap=risk.get("use_atr_position_cap", True),
        trailing_stop_atr_mult=env_float("TRAILING_STOP_ATR_MULT", risk.get("trailing_stop_atr_mult", 0.0)),  # 0 = off
        min_risk_reward=env_float("MIN_RISK_REWARD", risk.get("min_risk_reward", 1.0)),
        # Execution
        slippage_bps=env_float("SLIPPAGE_BPS", execution.get("slippage_bps", 5.0)),
        fee_bps=env_float("FEE_BPS", execution.get("fee_bps", 4.0)),
        # Telegram
        telegram_bot_token=env("TELEGRAM_BOT_TOKEN", telegram.get("bot_token", "")),
        telegram_chat_id=env("TELEGRAM_CHAT_ID", telegram.get("chat_id", "")),
        # Logging
        log_level=data.get("logging", {}).get("level", "INFO"),
        log_dir=Path(data.get("logging", {}).get("log_dir", "logs")),
        log_file=data.get("logging", {}).get("log_file", "trading_bot.log"),
        # Backtest
        backtest_start=data.get("backtest", {}).get("start_date"),
        backtest_end=data.get("backtest", {}).get("end_date"),
        backtest_initial_capital=float(data.get("backtest", {}).get("initial_capital", 10000.0)),
    )


class Config:
    """Unified configuration. Immutable after load."""

    __slots__ = (
        "binance_api_key", "binance_api_secret", "use_testnet", "symbol", "timeframe", "leverage",
        "ema_fast", "ema_slow", "rsi_len", "atr_len", "atr_stop_mult", "atr_tp_mult",
        "vol_mult", "vol_ma_len", "rsi_long_min", "rsi_short_max", "cooldown_candles",
        "risk_per_trade_usd", "max_daily_loss_usd", "max_drawdown_pct", "min_notional",
        "max_position_pct_capital", "use_atr_position_cap", "trailing_stop_atr_mult", "min_risk_reward",
        "slippage_bps", "fee_bps",
        "telegram_bot_token", "telegram_chat_id",
        "log_level", "log_dir", "log_file",
        "backtest_start", "backtest_end", "backtest_initial_capital",
    )

    def __init__(
        self,
        binance_api_key: str = "",
        binance_api_secret: str = "",
        use_testnet: bool = True,
        symbol: str = "ZECUSDT",
        timeframe: str = "5m",
        leverage: int = 5,
        ema_fast: int = 9,
        ema_slow: int = 21,
        rsi_len: int = 7,
        atr_len: int = 14,
        atr_stop_mult: float = 0.8,
        atr_tp_mult: float = 1.6,
        vol_mult: float = 1.5,
        vol_ma_len: int = 20,
        rsi_long_min: float = 48,
        rsi_short_max: float = 52,
        cooldown_candles: int = 1,
        risk_per_trade_usd: float = 10.0,
        max_daily_loss_usd: float = 50.0,
        max_drawdown_pct: float = 20.0,
        min_notional: float = 5.0,
        max_position_pct_capital: float = 100.0,
        use_atr_position_cap: bool = True,
        trailing_stop_atr_mult: float = 0.0,
        min_risk_reward: float = 1.0,
        slippage_bps: float = 5.0,
        fee_bps: float = 4.0,
        telegram_bot_token: str = "",
        telegram_chat_id: str = "",
        log_level: str = "INFO",
        log_dir: Path = None,
        log_file: str = "trading_bot.log",
        backtest_start: Optional[str] = None,
        backtest_end: Optional[str] = None,
        backtest_initial_capital: float = 10000.0,
    ):
        self.binance_api_key = binance_api_key
        self.binance_api_secret = binance_api_secret
        self.use_testnet = use_testnet
        self.symbol = symbol
        self.timeframe = timeframe
        self.leverage = leverage
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.rsi_len = rsi_len
        self.atr_len = atr_len
        self.atr_stop_mult = atr_stop_mult
        self.atr_tp_mult = atr_tp_mult
        self.vol_mult = vol_mult
        self.vol_ma_len = vol_ma_len
        self.rsi_long_min = rsi_long_min
        self.rsi_short_max = rsi_short_max
        self.cooldown_candles = cooldown_candles
        self.risk_per_trade_usd = risk_per_trade_usd
        self.max_daily_loss_usd = max_daily_loss_usd
        self.max_drawdown_pct = max_drawdown_pct
        self.min_notional = min_notional
        self.max_position_pct_capital = max_position_pct_capital
        self.use_atr_position_cap = use_atr_position_cap
        self.trailing_stop_atr_mult = trailing_stop_atr_mult
        self.min_risk_reward = min_risk_reward
        self.slippage_bps = slippage_bps
        self.fee_bps = fee_bps
        self.telegram_bot_token = telegram_bot_token
        self.telegram_chat_id = telegram_chat_id
        self.log_level = log_level
        self.log_dir = Path(log_dir) if log_dir else Path("logs")
        self.log_file = log_file
        self.backtest_start = backtest_start
        self.backtest_end = backtest_end
        self.backtest_initial_capital = backtest_initial_capital
