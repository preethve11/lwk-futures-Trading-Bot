"""
Risk manager: position sizing, daily loss cap, max drawdown, risk-reward check.
Position size = risk_usd / stop_distance (correct: lose risk_usd if stop hit).
"""

from __future__ import annotations
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Optional

from trading_bot.core.types import SignalSide
from trading_bot.utils.exchange_filters import round_quantity, parse_symbol_filters

logger = logging.getLogger("trading_bot.risk")


@dataclass
class RiskResult:
    """Result of risk check: allowed or rejected + reason."""
    allowed: bool
    quantity: float = 0.0
    reason: str = ""


class RiskManager:
    """
    Enforces: risk per trade (dollar loss at stop), daily loss cap,
    max drawdown, min notional, min risk-reward, optional ATR-based cap.
    """

    def __init__(
        self,
        risk_per_trade_usd: float,
        max_daily_loss_usd: float,
        max_drawdown_pct: float,
        min_notional: float,
        max_position_pct_capital: float,
        min_risk_reward: float,
        use_atr_position_cap: bool = True,
        trailing_stop_atr_mult: float = 0.0,
        symbol_info: Optional[dict] = None,
    ):
        self.risk_per_trade_usd = risk_per_trade_usd
        self.max_daily_loss_usd = max_daily_loss_usd
        self.max_drawdown_pct = max_drawdown_pct
        self.min_notional = min_notional
        self.max_position_pct_capital = max_position_pct_capital
        self.min_risk_reward = min_risk_reward
        self.use_atr_position_cap = use_atr_position_cap
        self.trailing_stop_atr_mult = trailing_stop_atr_mult
        self._min_qty, self._lot_step, self._price_tick = parse_symbol_filters(symbol_info)
        # State (for live: updated from execution)
        self._daily_loss: float = 0.0
        self._daily_reset_date: Optional[date] = None
        self._peak_equity: float = 0.0
        self._current_equity: float = 0.0
        self._consecutive_losses: int = 0

    def set_equity(self, equity: float) -> None:
        """Update current equity for drawdown check."""
        self._current_equity = equity
        if equity > self._peak_equity:
            self._peak_equity = equity

    def set_daily_loss(self, loss_usd: float, as_of_date: Optional[date] = None) -> None:
        """Set daily realized loss (e.g. from exchange). Reset if date changed."""
        as_of_date = as_of_date or datetime.now(timezone.utc).date()
        if self._daily_reset_date != as_of_date:
            self._daily_reset_date = as_of_date
            self._daily_loss = 0.0
        self._daily_loss = max(0.0, loss_usd)

    def record_trade_pnl(self, pnl: float) -> None:
        """Record closed trade PnL for daily loss and consecutive loss count."""
        if pnl < 0:
            self._daily_loss += -pnl
            self._consecutive_losses += 1
        else:
            self._consecutive_losses = 0

    def check_daily_loss(self) -> bool:
        """Return False if daily loss cap reached."""
        if self._daily_loss >= self.max_daily_loss_usd:
            logger.warning("Daily loss cap reached: %.2f >= %.2f", self._daily_loss, self.max_daily_loss_usd)
            return False
        return True

    def check_drawdown(self) -> bool:
        """Return False if max drawdown exceeded."""
        if self._peak_equity <= 0:
            return True
        dd_pct = (self._peak_equity - self._current_equity) / self._peak_equity * 100
        if dd_pct >= self.max_drawdown_pct:
            logger.warning("Max drawdown exceeded: %.2f%% >= %.2f%%", dd_pct, self.max_drawdown_pct)
            return False
        return True

    def _risk_reward_ratio(self, entry: float, stop: float, tp: float, side: SignalSide) -> float:
        """Risk-reward ratio (reward/risk)."""
        risk = abs(entry - stop)
        if risk <= 0:
            return 0.0
        reward = abs(tp - entry)
        return reward / risk

    def validate_signal(
        self,
        entry_price: float,
        stop_price: float,
        tp_price: float,
        side: SignalSide,
        atr: float,
        equity: Optional[float] = None,
    ) -> RiskResult:
        """
        Validate signal and compute allowed quantity.
        Position size = risk_per_trade_usd / |entry - stop| (so loss at stop = risk_per_trade_usd).
        """
        dist = abs(entry_price - stop_price)
        if dist <= 0:
            return RiskResult(allowed=False, reason="zero stop distance")

        # Min risk-reward
        rr = self._risk_reward_ratio(entry_price, stop_price, tp_price, side)
        if rr < self.min_risk_reward:
            return RiskResult(allowed=False, reason=f"risk_reward {rr:.2f} < {self.min_risk_reward}")

        # Quantity: lose exactly risk_per_trade_usd if stop hit
        qty = self.risk_per_trade_usd / dist
        qty = round_quantity(qty, self._min_qty, self._lot_step)
        if qty <= 0:
            return RiskResult(allowed=False, reason="qty rounded to 0")

        notional = qty * entry_price
        if notional < self.min_notional:
            return RiskResult(allowed=False, reason=f"notional {notional:.2f} < min {self.min_notional}")

        if equity is not None and equity > 0:
            max_notional = equity * (self.max_position_pct_capital / 100.0)
            if notional > max_notional:
                qty = round_quantity(max_notional / entry_price, self._min_qty, self._lot_step)
                if qty < self._min_qty:
                    return RiskResult(allowed=False, reason="position would exceed capital limit")

        # Optional ATR-based cap (reduce size in very high vol)
        if self.use_atr_position_cap and atr > 0 and entry_price > 0:
            # Cap notional to e.g. 2 * ATR * some scale to avoid oversized position in spikes
            atr_pct = atr / entry_price * 100
            if atr_pct > 5.0:  # cap when ATR > 5% of price
                scale = 5.0 / atr_pct
                qty = round_quantity(qty * scale, self._min_qty, self._lot_step)
                if qty < self._min_qty:
                    return RiskResult(allowed=False, reason="ATR cap reduced qty below min")

        if not self.check_daily_loss():
            return RiskResult(allowed=False, reason="daily loss cap")
        if equity is not None and not self.check_drawdown():
            return RiskResult(allowed=False, reason="max drawdown")

        return RiskResult(allowed=True, quantity=qty, reason="")

    def update_symbol_info(self, symbol_info: Optional[dict]) -> None:
        """Update lot/price filters when symbol or exchange info changes."""
        self._min_qty, self._lot_step, self._price_tick = parse_symbol_filters(symbol_info)
