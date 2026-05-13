"""
Backtest engine: no lookahead, closed bar only, slippage and fee simulation.
"""

from __future__ import annotations

import csv
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional, cast

import pandas as pd

from trading_bot.analytics.regime import add_regime_labels
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
    rejected_signals: dict[str, int] = field(default_factory=dict)
    executed_signals: int = 0
    period_start: datetime | None = None
    period_end: datetime | None = None

    @property
    def total_signals_evaluated(self) -> int:
        """Return all executed and rejected signal outcomes."""
        return self.executed_signals + sum(self.rejected_signals.values())

    @property
    def rejection_rate(self) -> float:
        """Return rejected outcomes divided by all signal outcomes."""
        total = self.total_signals_evaluated
        if total <= 0:
            return 0.0
        return sum(self.rejected_signals.values()) / total

    def rejected_signal_summary(self) -> dict[str, object]:
        """Return a JSON-serializable rejected-signal summary."""
        period = ""
        if self.period_start is not None and self.period_end is not None:
            period = f"{self.period_start.isoformat()} to {self.period_end.isoformat()}"
        return {
            "period": period,
            "total_signals_evaluated": self.total_signals_evaluated,
            "executed_trades": len(self.trades),
            "executed_signals": self.executed_signals,
            "rejection_rate": self.rejection_rate,
            "rejections": self.rejected_signals,
        }


@dataclass
class OpenBacktestPosition:
    """Open simulated position state."""

    side: SignalSide
    entry_price: float
    quantity: float
    stop_price: float
    take_profit_price: float
    entry_time: datetime
    entry_index: int
    volatility_regime: str = ""
    trend_regime: str = ""
    volume_regime: str = ""
    range_width_pct: float = 0.0
    ema_50: float = 0.0
    adx_14: float = 0.0
    intended_sl_pct: float = 0.0
    intended_tp_pct: float = 0.0
    session_name: str = ""
    session_open_time_utc: str = ""
    trailing_stop_atr_mult: float = 0.0
    max_holding_bars: int = 0
    exit_on_ema50_cross: bool = False
    exit_on_ranging_regime: bool = False
    best_price: float = 0.0
    funding_rate: float = 0.0
    funding_rate_delta_8h: float = 0.0
    open_interest_change_pct: float = 0.0
    adl_quantile: float = 0.0
    liquidation_spike_ratio: float = 0.0
    spread_proxy_bps: float = 0.0
    expected_edge_bps: float = 0.0
    expected_cost_bps: float = 0.0
    day_of_week: int = -1
    hour_of_day: int = -1
    strategy_id: str = ""


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
        add_regime_labels_to_trades: bool = False,
    ):
        self.strategy = strategy
        self.risk_manager = risk_manager
        self.initial_capital = initial_capital
        self.slippage_bps = slippage_bps
        self.fee_bps = fee_bps
        self.recorder = recorder
        self.add_regime_labels_to_trades = add_regime_labels_to_trades

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
        if self.add_regime_labels_to_trades:
            df = add_regime_labels(df)
        self.strategy.reset_signal_tracking()
        capital = self.initial_capital
        self.risk_manager.set_equity(capital)
        self.risk_manager.set_daily_loss(0.0)
        equity_curve = [capital]
        trades: List[Trade] = []
        open_pos: Optional[OpenBacktestPosition] = None
        cooldown_bars = 0
        last_bar_date = None
        min_bars = max(
            getattr(self.strategy, "ema_slow", 21),
            getattr(self.strategy, "atr_len", 14),
            getattr(self.strategy, "vol_ma_len", 20),
        ) + 2

        # Keep one future candle available for exit simulation. Otherwise the
        # engine can open a position on the final bar and mark it end_of_data
        # at the same timestamp, which produces impossible zero-duration trades.
        for i in range(min_bars, max(min_bars, len(df) - 1)):
            bar = df.iloc[i]
            bar_time = bar["time"] if isinstance(bar["time"], datetime) else pd.Timestamp(bar["time"])
            bar_date = bar_time.date() if hasattr(bar_time, "date") else pd.Timestamp(bar_time).date()
            if last_bar_date is not None and bar_date != last_bar_date:
                self.risk_manager.set_daily_loss(0.0, bar_date)
            last_bar_date = bar_date
            high, low = float(bar["high"]), float(bar["low"])
            slip_mult = 1 + self.slippage_bps / 10000.0

            if open_pos is not None:
                side = open_pos.side
                entry_price = open_pos.entry_price
                qty = open_pos.quantity
                _update_trailing_stop(open_pos, bar, high=high, low=low)
                stop = open_pos.stop_price
                tp = open_pos.take_profit_price
                entry_time = open_pos.entry_time
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
                if exit_price is None:
                    exit_price, exit_reason = _strategy_exit(open_pos, bar, i)
                if exit_price is not None:
                    exit_price_adj = exit_price / slip_mult if side == SignalSide.LONG else exit_price * slip_mult
                    fee = (qty * entry_price + qty * exit_price_adj) * (self.fee_bps / 10000.0)
                    pnl = (exit_price_adj - entry_price) * qty if side == SignalSide.LONG else (entry_price - exit_price_adj) * qty
                    pnl -= fee
                    pnl_pct = (pnl / (qty * entry_price)) * 100
                    target_approach_pct = _target_approach_pct(df, open_pos, i)
                    premature_stop = _premature_stop(df, open_pos, i) if exit_reason == "stop_loss" else False
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
                            intended_stop_loss=stop,
                            intended_take_profit=tp,
                            exit_slippage=exit_price_adj - exit_price,
                            premature_stop=premature_stop,
                            target_approach_pct=target_approach_pct,
                            volatility_regime=open_pos.volatility_regime,
                            trend_regime=open_pos.trend_regime,
                            volume_regime=open_pos.volume_regime,
                            range_width_pct=open_pos.range_width_pct,
                            ema_50=open_pos.ema_50,
                            adx_14=open_pos.adx_14,
                            intended_sl_pct=open_pos.intended_sl_pct,
                            intended_tp_pct=open_pos.intended_tp_pct,
                            session_name=open_pos.session_name,
                            session_open_time_utc=open_pos.session_open_time_utc,
                            funding_rate=open_pos.funding_rate,
                            funding_rate_delta_8h=open_pos.funding_rate_delta_8h,
                            open_interest_change_pct=open_pos.open_interest_change_pct,
                            adl_quantile=open_pos.adl_quantile,
                            liquidation_spike_ratio=open_pos.liquidation_spike_ratio,
                            spread_proxy_bps=open_pos.spread_proxy_bps,
                            expected_edge_bps=open_pos.expected_edge_bps,
                            expected_cost_bps=open_pos.expected_cost_bps,
                            day_of_week=open_pos.day_of_week,
                            hour_of_day=open_pos.hour_of_day,
                            strategy_id=open_pos.strategy_id,
                        )
                    )
                    equity_curve.append(capital)
                    open_pos = None
                    continue

            if open_pos is not None:
                self.strategy.record_rejection("existing_position")
                equity_curve.append(capital)
                continue

            if cooldown_bars > 0:
                self.strategy.record_rejection("other")
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
            risk_result = self.risk_manager.validate_signal(
                entry_price,
                raw_signal.stop_price,
                raw_signal.take_profit_price,
                raw_signal.side,
                atr,
                capital,
            )
            if not risk_result.allowed or risk_result.quantity <= 0:
                self.strategy.record_rejection("risk_limit")
                equity_curve.append(capital)
                continue

            qty = risk_result.quantity
            size_multiplier = _metadata_float(raw_signal.metadata, "position_size_multiplier", default=1.0)
            if size_multiplier <= 0:
                self.strategy.record_rejection("risk_limit")
                equity_curve.append(capital)
                continue
            qty *= min(size_multiplier, 1.0)
            entry_adj = entry_price * slip_mult if raw_signal.side == SignalSide.LONG else entry_price / slip_mult
            self.strategy.record_executed_signal()
            open_pos = OpenBacktestPosition(
                side=raw_signal.side,
                entry_price=entry_adj,
                quantity=qty,
                stop_price=raw_signal.stop_price,
                take_profit_price=raw_signal.take_profit_price,
                entry_time=bar_time,
                entry_index=i,
                volatility_regime=_bar_label(bar, "volatility_regime"),
                trend_regime=_bar_label(bar, "trend_regime"),
                volume_regime=_bar_label(bar, "volume_regime"),
                range_width_pct=_metadata_float(raw_signal.metadata, "range_width_pct"),
                ema_50=_metadata_float(raw_signal.metadata, "ema_50"),
                adx_14=_metadata_float(raw_signal.metadata, "adx_14"),
                intended_sl_pct=_metadata_float(raw_signal.metadata, "intended_sl_pct"),
                intended_tp_pct=_metadata_float(raw_signal.metadata, "intended_tp_pct"),
                session_name=_metadata_str(raw_signal.metadata, "session_name"),
                session_open_time_utc=_metadata_str(raw_signal.metadata, "session_open_time_utc"),
                trailing_stop_atr_mult=_metadata_float(raw_signal.metadata, "trailing_stop_atr_mult"),
                max_holding_bars=_metadata_int(raw_signal.metadata, "max_holding_bars"),
                exit_on_ema50_cross=_metadata_bool(raw_signal.metadata, "exit_on_ema50_cross"),
                exit_on_ranging_regime=_metadata_bool(raw_signal.metadata, "exit_on_ranging_regime"),
                best_price=entry_adj,
                funding_rate=_metadata_float(raw_signal.metadata, "funding_rate"),
                funding_rate_delta_8h=_metadata_float(raw_signal.metadata, "funding_rate_delta_8h"),
                open_interest_change_pct=_metadata_float(raw_signal.metadata, "open_interest_change_pct"),
                adl_quantile=_metadata_float(raw_signal.metadata, "adl_quantile"),
                liquidation_spike_ratio=_metadata_float(raw_signal.metadata, "liquidation_spike_ratio"),
                spread_proxy_bps=_metadata_float(raw_signal.metadata, "spread_proxy_bps"),
                expected_edge_bps=_metadata_float(raw_signal.metadata, "expected_edge_bps"),
                expected_cost_bps=_metadata_float(raw_signal.metadata, "expected_cost_bps"),
                day_of_week=_metadata_int(raw_signal.metadata, "day_of_week", default=-1),
                hour_of_day=_metadata_int(raw_signal.metadata, "hour_of_day", default=-1),
                strategy_id=_metadata_str(raw_signal.metadata, "strategy_id"),
            )
            cooldown_bars = getattr(self.strategy, "cooldown_candles", 1) if hasattr(self.strategy, "cooldown_candles") else 1
            equity_curve.append(capital)

        if open_pos is not None and len(df) > 0:
            side = open_pos.side
            entry_price = open_pos.entry_price
            qty = open_pos.quantity
            entry_time = open_pos.entry_time
            last_close = float(df.iloc[-1]["close"])
            pnl = (last_close - entry_price) * qty if side == SignalSide.LONG else (entry_price - last_close) * qty
            fee = 2 * (qty * entry_price) * (self.fee_bps / 10000.0)
            pnl -= fee
            target_approach_pct = _target_approach_pct(df, open_pos, len(df) - 1)
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
                    intended_stop_loss=open_pos.stop_price,
                    intended_take_profit=open_pos.take_profit_price,
                    exit_slippage=0.0,
                    target_approach_pct=target_approach_pct,
                    volatility_regime=open_pos.volatility_regime,
                    trend_regime=open_pos.trend_regime,
                    volume_regime=open_pos.volume_regime,
                    range_width_pct=open_pos.range_width_pct,
                    ema_50=open_pos.ema_50,
                    adx_14=open_pos.adx_14,
                    intended_sl_pct=open_pos.intended_sl_pct,
                    intended_tp_pct=open_pos.intended_tp_pct,
                    session_name=open_pos.session_name,
                    session_open_time_utc=open_pos.session_open_time_utc,
                    funding_rate=open_pos.funding_rate,
                    funding_rate_delta_8h=open_pos.funding_rate_delta_8h,
                    open_interest_change_pct=open_pos.open_interest_change_pct,
                    adl_quantile=open_pos.adl_quantile,
                    liquidation_spike_ratio=open_pos.liquidation_spike_ratio,
                    spread_proxy_bps=open_pos.spread_proxy_bps,
                    expected_edge_bps=open_pos.expected_edge_bps,
                    expected_cost_bps=open_pos.expected_cost_bps,
                    day_of_week=open_pos.day_of_week,
                    hour_of_day=open_pos.hour_of_day,
                    strategy_id=open_pos.strategy_id,
                )
            )
            equity_curve.append(capital)

        pnls = [t.pnl for t in trades]
        cum = [self.initial_capital]
        for pnl in pnls:
            cum.append(cum[-1] + pnl)
        metrics = compute_metrics(pnls, cumulative_returns=[value / self.initial_capital for value in cum])
        result = BacktestResult(
            trades=trades,
            equity_curve=equity_curve,
            metrics=metrics,
            rejected_signals=self.strategy.rejected_signals,
            executed_signals=self.strategy.executed_signals,
            period_start=_to_datetime(df.iloc[0]["time"]) if len(df) else None,
            period_end=_to_datetime(df.iloc[-1]["time"]) if len(df) else None,
        )
        if self.recorder is not None:
            self.recorder(result, symbol, start_date, end_date)
        return result


class BacktestArtifactExporter:
    """Export backtest diagnostics for strategy research."""

    TRADE_FIELDS = [
        "run",
        "symbol",
        "timeframe",
        "market_condition",
        "side",
        "quantity",
        "entry_price",
        "exit_price",
        "intended_stop_loss",
        "intended_take_profit",
        "exit_slippage",
        "entry_time",
        "exit_time",
        "duration_minutes",
        "pnl",
        "pnl_pct",
        "fees",
        "slippage_usd",
        "exit_reason",
        "premature_stop",
        "target_approach_pct",
        "volatility_regime",
        "trend_regime",
        "volume_regime",
        "signal_rejected_reason",
        "range_width_pct",
        "ema_50",
        "adx_14",
        "intended_sl_pct",
        "intended_tp_pct",
        "session_name",
        "session_open_time_utc",
        "funding_rate",
        "funding_rate_delta_8h",
        "open_interest_change_pct",
        "adl_quantile",
        "liquidation_spike_ratio",
        "spread_proxy_bps",
        "expected_edge_bps",
        "expected_cost_bps",
        "day_of_week",
        "hour_of_day",
        "strategy_id",
    ]

    @classmethod
    def write_trade_log(
        cls,
        result: BacktestResult,
        path: Path,
        *,
        run_name: str = "",
        timeframe: str = "",
        market_condition: str = "",
    ) -> Path:
        """Write closed trades to a CSV compatible with strategy-research."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=cls.TRADE_FIELDS)
            writer.writeheader()
            for trade in result.trades:
                writer.writerow(_trade_row(trade, run_name, timeframe, market_condition))
        return path

    @staticmethod
    def write_rejected_signals(result: BacktestResult, path: Path) -> Path:
        """Write rejected-signal counters to JSON."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result.rejected_signal_summary(), indent=2), encoding="utf-8")
        return path

    @classmethod
    def write_latest(
        cls,
        result: BacktestResult,
        output_dir: Path,
        *,
        run_name: str = "",
        timeframe: str = "",
    ) -> tuple[Path, Path]:
        """Write standard latest backtest artifacts and return trade/rejection paths."""
        trade_log = cls.write_trade_log(result, output_dir / "trade_log.csv", run_name=run_name, timeframe=timeframe)
        rejected = cls.write_rejected_signals(result, output_dir / "rejected_signals.json")
        return trade_log, rejected


def _trade_row(trade: Trade, run_name: str, timeframe: str, market_condition: str) -> dict[str, object]:
    condition = market_condition or _market_condition(
        trade.volatility_regime,
        trade.trend_regime,
        trade.volume_regime,
    )
    run = run_name or (f"{trade.symbol}_{timeframe}" if timeframe else trade.symbol)
    return {
        "run": run,
        "symbol": trade.symbol,
        "timeframe": timeframe,
        "market_condition": condition,
        "side": trade.side.name,
        "quantity": trade.quantity,
        "entry_price": trade.entry_price,
        "exit_price": trade.exit_price,
        "intended_stop_loss": trade.intended_stop_loss,
        "intended_take_profit": trade.intended_take_profit,
        "exit_slippage": trade.exit_slippage,
        "entry_time": _format_datetime(trade.entry_time),
        "exit_time": _format_datetime(trade.exit_time),
        "duration_minutes": _duration_minutes(trade.entry_time, trade.exit_time),
        "pnl": trade.pnl,
        "pnl_pct": trade.pnl_pct,
        "fees": trade.fees,
        "slippage_usd": trade.slippage_usd,
        "exit_reason": trade.exit_reason,
        "premature_stop": trade.premature_stop,
        "target_approach_pct": trade.target_approach_pct,
        "volatility_regime": trade.volatility_regime,
        "trend_regime": trade.trend_regime,
        "volume_regime": trade.volume_regime,
        "signal_rejected_reason": trade.signal_rejected_reason,
        "range_width_pct": trade.range_width_pct,
        "ema_50": trade.ema_50,
        "adx_14": trade.adx_14,
        "intended_sl_pct": trade.intended_sl_pct,
        "intended_tp_pct": trade.intended_tp_pct,
        "session_name": trade.session_name,
        "session_open_time_utc": trade.session_open_time_utc,
        "funding_rate": trade.funding_rate,
        "funding_rate_delta_8h": trade.funding_rate_delta_8h,
        "open_interest_change_pct": trade.open_interest_change_pct,
        "adl_quantile": trade.adl_quantile,
        "liquidation_spike_ratio": trade.liquidation_spike_ratio,
        "spread_proxy_bps": trade.spread_proxy_bps,
        "expected_edge_bps": trade.expected_edge_bps,
        "expected_cost_bps": trade.expected_cost_bps,
        "day_of_week": trade.day_of_week,
        "hour_of_day": trade.hour_of_day,
        "strategy_id": trade.strategy_id,
    }


def _market_condition(volatility: str, trend: str, volume: str) -> str:
    labels = [label.lower() for label in (trend, volatility, volume) if label]
    return "_".join(labels) if labels else "unknown"


def _duration_minutes(start: datetime, end: datetime) -> float:
    return (end - start).total_seconds() / 60.0


def _format_datetime(value: datetime) -> str:
    return value.isoformat()


def _bar_label(row: pd.Series, column: str) -> str:
    if column not in row:
        return ""
    value = row[column]
    if pd.isna(value):
        return ""
    return str(value)


def _metadata_float(metadata: dict[str, object], key: str, *, default: float = 0.0) -> float:
    value = metadata.get(key)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return default
    return default


def _metadata_int(metadata: dict[str, object], key: str, *, default: int = 0) -> int:
    value = metadata.get(key)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value))
        except ValueError:
            return default
    return default


def _metadata_bool(metadata: dict[str, object], key: str) -> bool:
    value = metadata.get(key)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    if isinstance(value, int):
        return value != 0
    return False


def _metadata_str(metadata: dict[str, object], key: str) -> str:
    value = metadata.get(key)
    return str(value) if value is not None else ""


def _target_approach_pct(df: pd.DataFrame, position: OpenBacktestPosition, exit_index: int) -> float:
    """Return how far price moved toward the planned target before exit."""
    if position.side == SignalSide.LONG:
        target_distance = position.take_profit_price - position.entry_price
        if target_distance <= 0:
            return 0.0
        max_favorable = float(df.iloc[position.entry_index : exit_index + 1]["high"].max()) - position.entry_price
    else:
        target_distance = position.entry_price - position.take_profit_price
        if target_distance <= 0:
            return 0.0
        max_favorable = position.entry_price - float(df.iloc[position.entry_index : exit_index + 1]["low"].min())
    return max(0.0, (max_favorable / target_distance) * 100.0)


def _premature_stop(
    df: pd.DataFrame,
    position: OpenBacktestPosition,
    exit_index: int,
    *,
    lookahead_bars: int = 10,
) -> bool:
    """Return True when price hits the planned target shortly after a simulated stop."""
    future = df.iloc[exit_index + 1 : exit_index + 1 + lookahead_bars]
    if future.empty:
        return False
    if position.side == SignalSide.LONG:
        return bool(float(future["high"].max()) >= position.take_profit_price)
    return bool(float(future["low"].min()) <= position.take_profit_price)


def _update_trailing_stop(open_pos: OpenBacktestPosition, bar: pd.Series, *, high: float, low: float) -> None:
    """Update an open position's stop when strategy metadata enabled ATR trailing."""
    if open_pos.trailing_stop_atr_mult <= 0:
        return
    atr = _bar_float(bar, "atr_14") or _bar_float(bar, "atr")
    if atr <= 0:
        return
    if open_pos.side == SignalSide.LONG:
        open_pos.best_price = max(open_pos.best_price, high)
        open_pos.stop_price = max(open_pos.stop_price, open_pos.best_price - atr * open_pos.trailing_stop_atr_mult)
    else:
        open_pos.best_price = min(open_pos.best_price, low)
        open_pos.stop_price = min(open_pos.stop_price, open_pos.best_price + atr * open_pos.trailing_stop_atr_mult)


def _strategy_exit(open_pos: OpenBacktestPosition, bar: pd.Series, index: int) -> tuple[float | None, str]:
    """Return a strategy-managed exit price/reason when metadata gates request one."""
    close = _bar_float(bar, "close")
    if close <= 0:
        return None, ""
    if open_pos.max_holding_bars > 0 and index - open_pos.entry_index >= open_pos.max_holding_bars:
        return close, "max_holding_time"
    if open_pos.exit_on_ema50_cross:
        ema_50 = _bar_float(bar, "ema_50")
        if ema_50 > 0:
            if open_pos.side == SignalSide.LONG and close < ema_50:
                return close, "ema50_exit"
            if open_pos.side == SignalSide.SHORT and close > ema_50:
                return close, "ema50_exit"
    if open_pos.exit_on_ranging_regime:
        trend_regime = _bar_label(bar, "trend_regime")
        trend_state = _bar_label(bar, "trend_state")
        if trend_regime == "RANGING" or trend_state == "RANGING":
            pnl = close - open_pos.entry_price if open_pos.side == SignalSide.LONG else open_pos.entry_price - close
            if pnl <= 0:
                return close, "regime_flip"
    return None, ""


def _bar_float(row: pd.Series, column: str) -> float:
    if column not in row:
        return 0.0
    value = row[column]
    if pd.isna(value):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except ValueError:
        return 0.0


def _to_datetime(value: object) -> datetime:
    if isinstance(value, pd.Timestamp):
        return cast(datetime, value.to_pydatetime())
    if isinstance(value, datetime):
        return value
    return cast(datetime, pd.Timestamp(value).to_pydatetime())
