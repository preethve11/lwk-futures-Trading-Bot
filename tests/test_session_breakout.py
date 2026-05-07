from __future__ import annotations

from pathlib import Path

import pandas as pd

from trading_bot.backtesting.engine import BacktestArtifactExporter, BacktestEngine
from trading_bot.core.types import SignalSide
from trading_bot.risk.manager import RiskManager
from trading_bot.strategies.session_breakout import SessionBreakoutStrategy


class _TestableSessionBreakoutStrategy(SessionBreakoutStrategy):
    def __init__(
        self,
        *,
        timeframe: str = "15m",
        min_range_width_pct: float = 0.4,
        min_adx: float = 20.0,
    ) -> None:
        super().__init__(
            timeframe=timeframe,
            sessions=["nse:03:45"],
            pre_open_minutes=120,
            trade_window_minutes=240,
            min_range_width_pct=min_range_width_pct,
            ema_length=50,
            adx_length=14,
            min_adx=min_adx,
            entry_buffer_pct=0.0,
            enabled_timeframes=["15m", "1h"],
        )

    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        enriched = super().compute_indicators(df)
        enriched["ema_50"] = 95.0
        enriched["adx_14"] = 30.0
        return enriched


def _risk_manager() -> RiskManager:
    return RiskManager(
        risk_per_trade_usd=10.0,
        max_daily_loss_usd=100.0,
        max_drawdown_pct=50.0,
        min_notional=1.0,
        max_position_pct_capital=100.0,
        min_risk_reward=1.0,
        use_atr_position_cap=False,
    )


def _session_data(*, range_high: float = 110.0, range_low: float = 100.0) -> pd.DataFrame:
    times = pd.date_range("2026-01-01T00:00:00Z", periods=128, freq="15min")
    rows = []
    for index, timestamp in enumerate(times):
        close = 96.0 + index * 0.05
        rows.append(
            {
                "time": timestamp,
                "open": close - 0.1,
                "high": close + 0.2,
                "low": close - 0.2,
                "close": close,
                "volume": 1000.0,
            }
        )
    df = pd.DataFrame(rows)
    pre_session = (df["time"] >= pd.Timestamp("2026-01-02T01:45:00Z")) & (
        df["time"] < pd.Timestamp("2026-01-02T03:45:00Z")
    )
    df.loc[pre_session, "high"] = range_high
    df.loc[pre_session, "low"] = range_low
    df.loc[pre_session, "close"] = (range_high + range_low) / 2.0
    breakout_time = df["time"] == pd.Timestamp("2026-01-02T04:00:00Z")
    df.loc[breakout_time, ["open", "low", "close"]] = [110.5, 110.0, 112.0]
    df.loc[breakout_time, "high"] = 112.0
    target_time = df["time"] == pd.Timestamp("2026-01-02T04:45:00Z")
    df.loc[target_time, "high"] = 121.0
    df.loc[target_time, "close"] = 120.5
    return df


def _history_for_signal(strategy: SessionBreakoutStrategy, df: pd.DataFrame) -> pd.DataFrame:
    enriched = strategy.compute_indicators(df)
    return enriched[enriched["time"] <= pd.Timestamp("2026-01-02T04:15:00Z")]


def test_session_breakout_rejects_narrow_range() -> None:
    strategy = _TestableSessionBreakoutStrategy()
    hist = _history_for_signal(strategy, _session_data(range_high=100.2, range_low=100.0))

    assert strategy.get_signal(hist) is None
    assert strategy.rejected_signals["range_too_narrow"] == 1


def test_session_breakout_rejects_counter_trend_ema() -> None:
    strategy = _TestableSessionBreakoutStrategy()
    hist = _history_for_signal(strategy, _session_data())
    hist.loc[:, "ema_50"] = 130.0

    assert strategy.get_signal(hist) is None
    assert strategy.rejected_signals["ema_regime_filter"] == 1


def test_session_breakout_rejects_choppy_adx() -> None:
    strategy = _TestableSessionBreakoutStrategy(min_adx=20.0)
    hist = _history_for_signal(strategy, _session_data())
    hist.loc[:, "adx_14"] = 10.0

    assert strategy.get_signal(hist) is None
    assert strategy.rejected_signals["adx_chop_filter"] == 1


def test_session_breakout_keeps_5m_disabled() -> None:
    strategy = _TestableSessionBreakoutStrategy(timeframe="5m")
    hist = _history_for_signal(strategy, _session_data())

    assert strategy.get_signal(hist) is None
    assert strategy.rejected_signals["timeframe_disabled"] == 1


def test_session_breakout_records_research_columns(tmp_path: Path) -> None:
    strategy = _TestableSessionBreakoutStrategy()
    engine = BacktestEngine(strategy=strategy, risk_manager=_risk_manager(), initial_capital=10_000)

    result = engine.run(_session_data(), symbol="ZECUSDT")

    assert result.trades
    trade = result.trades[0]
    assert trade.side == SignalSide.LONG
    assert trade.session_name == "nse"
    assert trade.range_width_pct > 0.4
    assert trade.intended_sl_pct > 0
    assert trade.intended_tp_pct > 0

    csv_path = BacktestArtifactExporter.write_trade_log(
        result,
        tmp_path / "trade_log.csv",
        run_name="ZECUSDT_15m",
        timeframe="15m",
    )
    header = csv_path.read_text(encoding="utf-8").splitlines()[0]
    assert "signal_rejected_reason" in header
    assert "intended_sl_pct" in header
    assert "session_name" in header
