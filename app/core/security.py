"""Runtime safety checks for live trading."""

from __future__ import annotations

from app.core.config import Settings


def assert_live_trading_allowed(settings: Settings) -> None:
    """Block mainnet trading unless the operator explicitly confirms it.

    Testnet runs are always allowed. Mainnet runs require
    CONFIRM_LIVE_TRADING=true so accidental real-money execution fails before
    any exchange call is made.
    """
    if settings.use_testnet:
        return
    if settings.enable_live_trading and settings.confirm_live_trading:
        return
    raise RuntimeError(
        "Live trading blocked: set ENABLE_LIVE_TRADING=true and CONFIRM_LIVE_TRADING=true only after "
        "validating the strategy and risk controls on Binance testnet."
    )
