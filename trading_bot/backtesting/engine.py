"""
Backtest engine: no lookahead, closed bar only, slippage and fee simulation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, List, Optional

import pandas as pd

from trading_bot.analytics.metrics import PerformanceMetrics, compute_metrics
from trading_bot.core.types import SignalSide, Trade
from trading_bot.risk.manager import RiskManager
from trading_bot.strategies.base import BaseStrategy

logger = logging.getLogger("trading_bot.backtest")


@dataclass
class BacktestResult:
    """Backtest output: trades and metrics."""

    trades: List[Trade] = field(default_factory=list)
    equity_curve: List[float] = field(default_factory=list)
    metrics: Optional[PerformanceMetrics] = None


BacktestRecorder = Callable[[BacktestResult, str, str | datetime | None, str | datetime | None], None]


class BacktestEngine:
    """
    Runs strategy on historical klines. Uses only closed bars (iloc up to -1).
    Simulates: slippage (bps), fees (bps), SL/TP exit on next bar.
    """

    def __init__(
        self,
        strategy: BaseStrategy,
        risk_manager: RiskManager,
        initial_capital: float = 10000.0,
        slippage_bps: float = 5.0,
        fee_bps: float = 4.0,
        recorder: BacktestRecorder | None = None,
    ):
        self.strategy = strategy
        self.risk_manager = risk_manager
        self.initial_capital = initial_capital
        self.slippage_bps = slippage_bps
        self.fee_bps = fee_bps
        self.recorder = recorder

    @staticmethod
    def _filter_date_range(
        df: pd.DataFrame,
        start_date: str | datetime | None,
        end_date: str | datetime | None,
    ) -> pd.DataFrame:
        """Return rows inside an inclusive time range."""
        if "time" not in df.columns:
            raise ValueError("Backtest DataFrame must include a 'time' column")

        filtered = df.copy()
        filtered["time"] = pd.to_datetime(filtered["time"], utc=True)
        if start_date is not None:
            start = pd.Timestamp(start_date)
            if start.tzinfo is None:
                start = start.tz_localize("UTC")
            filtered = filtered[filtered["time"] >= start]
        if end_date is not None:
            end = pd.Timestamp(end_date)
            if end.tzinfo is None:
                end = end.tz_localize("UTC")
            filtered = filtered[filtered["time"] <= end]
        return filtered.reset_index(drop=True)

    def run(
        self,
        df: pd.DataFrame,
        symbol: str = "ZECUSDT",
        start_date: str | datetime | None = None,
        end_date: str | datetime | None = None,
    ) -> BacktestResult:
        """
        Run backtest on OHLCV DataFrame (columns: time, open, high, low, close, volume).
        Iterates bar-by-bar; on each bar uses only data up to previous closed bar for signal.
        Optional start/end dates are inclusive and applied before indicators are computed.
        """
        df = self._filter_date_range(df, start_date, end_date)
        df = self.strategy.compute_indicators(df)
        capital = self.initial_capital
        self.risk_manager.set_equity(capital)
        self.risk_manager.set_daily_loss(0.0)
        equity_curve = [capital]
        trades: List[Trade] = []
        open_pos: Optional[tuple[SignalSide, float, float, float, float, datetime, int]] = None
        cooldown_bars = 0
        last_bar_date = None
        min_bars = max(
            getattr(self.strategy, "ema_slow", 21),
            getattr(self.strategy, "atr_len", 14),
            getattr(self.strategy, "vol_ma_len", 20),
        ) + 2

        for i in range(min_bars, len(df)):
            bar = df.iloc[i]
            bar_time = bar["time"] if isinstance(bar["time"], datetime) else pd.Timestamp(bar["time"])
            bar_date = bar_time.date() if hasattr(bar_time, "date") else pd.Timestamp(bar_time).date()
            if last_bar_date is not None and bar_date != last_bar_date:
                self.risk_manager.set_daily_loss(0.0, bar_date)
            last_bar_date = bar_date
            high, low = float(bar["high"]), float(bar["low"])
            slip_mult = 1 + self.slippage_bps / 10000.0

            if open_pos is not None:
                side, entry_price, qty, stop, tp, entry_time, _ = open_pos
                exit_price = None
                exit_reason = ""
                if side == SignalSide.LONG:
                    if low <= stop:
                        exit_price = stop
                        exit_reason = "stop_loss"
                    elif high >= tp:
                        exit_price = tp
                        exit_reason = "take_profit"
                else:
                    if high >= stop:
                        exit_price = stop
                        exit_reason = "stop_loss"
                    elif low <= tp:
                        exit_price = tp
                        exit_reason = "take_profit"
                if exit_price is not None:
                    exit_price_adj = exit_price / slip_mult if side == SignalSide.LONG else exit_price * slip_mult
                    fee = (qty * entry_price + qty * exit_price_adj) * (self.fee_bps / 10000.0)
                    pnl = (exit_price_adj - entry_price) * qty if side == SignalSide.LONG else (entry_price - exit_price_adj) * qty
                    pnl -= fee
                    pnl_pct = (pnl / (qty * entry_price)) * 100
                    capital += pnl
                    self.risk_manager.set_equity(capital)
                    self.risk_manager.record_trade_pnl(pnl)
                    trades.append(
                        Trade(
                            symbol=symbol,
                            side=side,
                            quantity=qty,
                            entry_price=entry_price,
                            exit_price=exit_price_adj,
                            pnl=pnl,
                            pnl_pct=pnl_pct,
                            entry_time=entry_time,
                            exit_time=bar_time,
                            exit_reason=exit_reason,
                            fees=fee,
                            slippage_usd=0.0,
                        )
                    )
                    equity_curve.append(capital)
                    open_pos = None
                    continue

            if open_pos is not None:
                equity_curve.append(capital)
                continue

            if cooldown_bars > 0:
                cooldown_bars -= 1
                equity_curve.append(capital)
                continue

            hist = df.iloc[:i]
            raw_signal = self.strategy.get_signal(hist)
            if raw_signal is None:
                equity_curve.append(capital)
                continue

            prev = df.iloc[i - 1]
            entry_price = raw_signal.entry_price
            atr = float(prev["atr"]) if not pd.isna(prev.get("atr")) else 0.0
            result = self.risk_manager.validate_signal(
                entry_price,
                raw_signal.stop_price,
                raw_signal.take_profit_price,
                raw_signal.side,
                atr,
                capital,
            )
            if not result.allowed or result.quantity <= 0:
                equity_curve.append(capital)
                continue

            qty = result.quantity
            entry_adj = entry_price * slip_mult if raw_signal.side == SignalSide.LONG else entry_price / slip_mult
            open_pos = (raw_signal.side, entry_adj, qty, raw_signal.stop_price, raw_signal.take_profit_price, bar_time, i)
            cooldown_bars = getattr(self.strategy, "cooldown_candles", 1) if hasattr(self.strategy, "cooldown_candles") else 1
            equity_curve.append(capital)

        if open_pos is not None and len(df) > 0:
            side, entry_price, qty, _, _, entry_time, _ = open_pos
            last_close = float(df.iloc[-1]["close"])
            pnl = (last_close - entry_price) * qty if side == SignalSide.LONG else (entry_price - last_close) * qty
            fee = 2 * (qty * entry_price) * (self.fee_bps / 10000.0)
            pnl -= fee
            capital += pnl
            trades.append(
                Trade(
                    symbol=symbol,
                    side=side,
                    quantity=qty,
                    entry_price=entry_price,
                    exit_price=last_close,
                    pnl=pnl,
                    pnl_pct=(pnl / (qty * entry_price)) * 100,
                    entry_time=entry_time,
                    exit_time=df.iloc[-1]["time"],
                    exit_reason="end_of_data",
                    fees=fee,
                )
            )
            equity_curve.append(capital)

        pnls = [t.pnl for t in trades]
        cum = [self.initial_capital]
        for pnl in pnls:
            cum.append(cum[-1] + pnl)
        metrics = compute_metrics(pnls, cumulative_returns=[value / self.initial_capital for value in cum])
        result = BacktestResult(trades=trades, equity_curve=equity_curve, metrics=metrics)
        if self.recorder is not None:
            self.recorder(result, symbol, start_date, end_date)
        return result
