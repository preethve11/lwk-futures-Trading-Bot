"""Read-only mainnet readiness checks."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.core.config import Settings


class ReadinessStatus(str, Enum):
    """Operator readiness result severity."""

    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass(frozen=True)
class ReadinessCheck:
    """One mainnet readiness checklist item."""

    name: str
    status: ReadinessStatus
    detail: str
    remediation: str = ""


@dataclass(frozen=True)
class MainnetReadinessReport:
    """Read-only report for mainnet dry-run and small-notional readiness."""

    checks: list[ReadinessCheck]

    @property
    def failed(self) -> list[ReadinessCheck]:
        return [check for check in self.checks if check.status == ReadinessStatus.FAIL]

    @property
    def warnings(self) -> list[ReadinessCheck]:
        return [check for check in self.checks if check.status == ReadinessStatus.WARN]

    @property
    def ready(self) -> bool:
        return not self.failed


def evaluate_mainnet_readiness(settings: Settings, *, small_notional_usd: float = 10.0) -> MainnetReadinessReport:
    """Evaluate local config readiness without network calls or order placement."""
    checks = [
        _mainnet_mode_check(settings),
        _live_confirmation_check(settings),
        _mainnet_credentials_check(settings),
        _api_token_check(settings),
        _database_url_check(settings),
        _database_migration_check(settings),
        _risk_per_trade_check(settings, small_notional_usd),
        _daily_loss_check(settings, small_notional_usd),
        _drawdown_check(settings),
        _strategy_gate_check(settings),
        _alerting_check(settings),
        _account_reconciliation_check(settings, small_notional_usd),
        _market_data_check(settings),
    ]
    return MainnetReadinessReport(checks=checks)


def format_mainnet_readiness_report(report: MainnetReadinessReport) -> str:
    """Render the readiness report for CLI output."""
    lines = ["--- Mainnet Dry-Run Readiness ---"]
    for check in report.checks:
        lines.append(f"[{check.status.value}] {check.name}: {check.detail}")
        if check.remediation:
            lines.append(f"      Fix: {check.remediation}")
    lines.append(f"Summary: {len(report.failed)} failed, {len(report.warnings)} warnings")
    return "\n".join(lines)


def _mainnet_mode_check(settings: Settings) -> ReadinessCheck:
    if settings.use_testnet:
        return ReadinessCheck(
            name="Mainnet mode",
            status=ReadinessStatus.FAIL,
            detail="USE_TESTNET is true, so this configuration is still pointed at testnet.",
            remediation="Set USE_TESTNET=false only for the final dry run immediately before a supervised mainnet test.",
        )
    return ReadinessCheck(
        name="Mainnet mode",
        status=ReadinessStatus.PASS,
        detail="USE_TESTNET is false.",
    )


def _live_confirmation_check(settings: Settings) -> ReadinessCheck:
    if settings.confirm_live_trading:
        return ReadinessCheck(
            name="Live trading confirmation",
            status=ReadinessStatus.PASS,
            detail="CONFIRM_LIVE_TRADING is true.",
        )
    return ReadinessCheck(
        name="Live trading confirmation",
        status=ReadinessStatus.FAIL,
        detail="CONFIRM_LIVE_TRADING is false; live mainnet execution is blocked.",
        remediation="Set CONFIRM_LIVE_TRADING=true only during a supervised small-notional mainnet window.",
    )


def _mainnet_credentials_check(settings: Settings) -> ReadinessCheck:
    if settings.binance_mainnet_api_key and settings.binance_mainnet_api_secret:
        return ReadinessCheck(
            name="Mainnet API credentials",
            status=ReadinessStatus.PASS,
            detail="Mainnet Binance key and secret are configured.",
        )
    return ReadinessCheck(
        name="Mainnet API credentials",
        status=ReadinessStatus.FAIL,
        detail="BINANCE_MAINNET_API_KEY or BINANCE_MAINNET_API_SECRET is missing.",
        remediation="Provide mainnet keys through environment or secret manager; never commit them.",
    )


def _api_token_check(settings: Settings) -> ReadinessCheck:
    if settings.api_token:
        return ReadinessCheck(
            name="API token",
            status=ReadinessStatus.PASS,
            detail="API_TOKEN is configured.",
        )
    return ReadinessCheck(
        name="API token",
        status=ReadinessStatus.FAIL,
        detail="API_TOKEN is empty.",
        remediation="Set API_TOKEN before exposing dashboard/API or running mainnet.",
    )


def _database_url_check(settings: Settings) -> ReadinessCheck:
    if settings.database_url.startswith("postgresql"):
        return ReadinessCheck(
            name="Database backend",
            status=ReadinessStatus.PASS,
            detail="DATABASE_URL points to Postgres.",
        )
    return ReadinessCheck(
        name="Database backend",
        status=ReadinessStatus.WARN,
        detail="DATABASE_URL does not point to Postgres.",
        remediation="Use Postgres for any durable mainnet test; SQLite is acceptable only for local rehearsals.",
    )


def _database_migration_check(settings: Settings) -> ReadinessCheck:
    if not settings.database_auto_create_tables:
        return ReadinessCheck(
            name="Migration discipline",
            status=ReadinessStatus.PASS,
            detail="DATABASE_AUTO_CREATE_TABLES is false.",
        )
    return ReadinessCheck(
        name="Migration discipline",
        status=ReadinessStatus.WARN,
        detail="DATABASE_AUTO_CREATE_TABLES is true.",
        remediation="Run `py main.py db-upgrade --revision head` and set DATABASE_AUTO_CREATE_TABLES=false for production-like mainnet.",
    )


def _risk_per_trade_check(settings: Settings, small_notional_usd: float) -> ReadinessCheck:
    if settings.risk_per_trade_usd <= small_notional_usd:
        return ReadinessCheck(
            name="Small-notional risk",
            status=ReadinessStatus.PASS,
            detail=f"RISK_PER_TRADE_USD={settings.risk_per_trade_usd:.2f} is within {small_notional_usd:.2f}.",
        )
    return ReadinessCheck(
        name="Small-notional risk",
        status=ReadinessStatus.FAIL,
        detail=f"RISK_PER_TRADE_USD={settings.risk_per_trade_usd:.2f} exceeds {small_notional_usd:.2f}.",
        remediation="Lower RISK_PER_TRADE_USD for the first mainnet test window.",
    )


def _daily_loss_check(settings: Settings, small_notional_usd: float) -> ReadinessCheck:
    cap = small_notional_usd * 3
    if settings.max_daily_loss_usd <= cap:
        return ReadinessCheck(
            name="Daily loss cap",
            status=ReadinessStatus.PASS,
            detail=f"MAX_DAILY_LOSS_USD={settings.max_daily_loss_usd:.2f} is within {cap:.2f}.",
        )
    return ReadinessCheck(
        name="Daily loss cap",
        status=ReadinessStatus.FAIL,
        detail=f"MAX_DAILY_LOSS_USD={settings.max_daily_loss_usd:.2f} exceeds {cap:.2f}.",
        remediation="For first mainnet, cap daily loss at no more than 3x the small-notional risk budget.",
    )


def _drawdown_check(settings: Settings) -> ReadinessCheck:
    if settings.max_drawdown_pct <= 10:
        return ReadinessCheck(
            name="Drawdown lock",
            status=ReadinessStatus.PASS,
            detail=f"MAX_DRAWDOWN_PCT={settings.max_drawdown_pct:.2f} is conservative.",
        )
    return ReadinessCheck(
        name="Drawdown lock",
        status=ReadinessStatus.WARN,
        detail=f"MAX_DRAWDOWN_PCT={settings.max_drawdown_pct:.2f} is not conservative for first mainnet.",
        remediation="Use 10% or lower for first small-notional validation.",
    )


def _strategy_gate_check(settings: Settings) -> ReadinessCheck:
    if settings.live_strategy_gate_required_for_mainnet:
        return ReadinessCheck(
            name="Strategy performance gate",
            status=ReadinessStatus.PASS,
            detail=(
                "Mainnet live startup requires the latest backtest to pass "
                f"{settings.live_gate_min_trades} trades, profit factor {settings.live_gate_min_profit_factor:.2f}, "
                f"expectancy {settings.live_gate_min_expectancy_usd:.2f}, Sharpe {settings.live_gate_min_sharpe:.2f}, "
                f"and max drawdown {settings.live_gate_max_drawdown_pct:.2f}%."
            ),
        )
    return ReadinessCheck(
        name="Strategy performance gate",
        status=ReadinessStatus.FAIL,
        detail="LIVE_STRATEGY_GATE_REQUIRED_FOR_MAINNET is false.",
        remediation="Keep the strategy performance gate required for mainnet live trading.",
    )


def _alerting_check(settings: Settings) -> ReadinessCheck:
    if settings.telegram_bot_token and settings.telegram_chat_id:
        return ReadinessCheck(
            name="Operator alerts",
            status=ReadinessStatus.PASS,
            detail="Telegram alert token and chat are configured.",
        )
    return ReadinessCheck(
        name="Operator alerts",
        status=ReadinessStatus.WARN,
        detail="Telegram alert token or chat is missing.",
        remediation="Configure Telegram before mainnet so emergency and drift alerts leave the process.",
    )


def _account_reconciliation_check(settings: Settings, small_notional_usd: float) -> ReadinessCheck:
    if settings.account_reconciliation_interval_seconds <= 300 and settings.account_equity_drift_threshold_usd <= small_notional_usd:
        return ReadinessCheck(
            name="Account/equity reconciliation",
            status=ReadinessStatus.PASS,
            detail=(
                "Account reconciliation interval and drift threshold are tight enough "
                f"({settings.account_reconciliation_interval_seconds}s, {settings.account_equity_drift_threshold_usd:.2f} USD)."
            ),
        )
    return ReadinessCheck(
        name="Account/equity reconciliation",
        status=ReadinessStatus.WARN,
        detail=(
            "Account reconciliation settings may be too loose for first mainnet "
            f"({settings.account_reconciliation_interval_seconds}s, {settings.account_equity_drift_threshold_usd:.2f} USD)."
        ),
        remediation="Use <=300 seconds and drift threshold <= the small-notional risk budget.",
    )


def _market_data_check(settings: Settings) -> ReadinessCheck:
    if settings.market_data_source == "redis":
        return ReadinessCheck(
            name="Market data source",
            status=ReadinessStatus.PASS,
            detail="Live loop is configured for Redis market data.",
        )
    return ReadinessCheck(
        name="Market data source",
        status=ReadinessStatus.WARN,
        detail="Live loop is configured for REST polling.",
        remediation="REST polling is acceptable for a supervised first test; Redis WebSocket market data is preferred afterward.",
    )
