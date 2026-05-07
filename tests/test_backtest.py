from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from app.backtesting.data_loader import BinanceHistoricalDataLoader, load_csv_ohlcv
from app.backtesting.multi_symbol import BacktestReportExporter, MultiSymbolBacktestRunner
from app.core.config import Settings
from app.persistence.database import create_session_factory, init_db, session_scope
from app.persistence.repositories import TradeRepository
from trading_bot.backtesting.engine import BacktestEngine
from trading_bot.core.types import Signal, SignalSide
from trading_bot.risk.manager import RiskManager
from trading_bot.strategies.base import BaseStrategy


class AlwaysLongStrategy(BaseStrategy):
    ema_slow = 2
    atr_len = 2
    vol_ma_len = 2
    cooldown_candles = 0

    def __init__(self) -> None:
        self.observed_last_closed_times: list[pd.Timestamp] = []

    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        enriched = df.copy()
        enriched["atr"] = 1.0
        return enriched

    def get_signal(self, df: pd.DataFrame, **kwargs: object) -> Signal | None:
        if len(df) < 4:
            return None
        last_closed = df.iloc[-2]
        timestamp = pd.Timestamp(last_closed["time"])
        self.observed_last_closed_times.append(timestamp)
        entry = float(last_closed["close"])
        return Signal(
            side=SignalSide.LONG,
            entry_price=entry,
            stop_price=entry - 1.0,
            take_profit_price=entry + 2.0,
            quantity=0.0,
            timestamp=timestamp.to_pydatetime(),
            metadata={"reason": "test"},
        )


class FakeBinanceClient:
    def __init__(self, rows: list[list[object]]) -> None:
        self.rows = rows
        self.calls = 0

    def futures_klines(
        self,
        *,
        symbol: str,
        interval: str,
        startTime: int | None = None,
        endTime: int | None = None,
        limit: int = 1500,
    ) -> list[list[object]]:
        self.calls += 1
        filtered = [row for row in self.rows if (startTime is None or int(row[0]) >= startTime)]
        if endTime is not None:
            filtered = [row for row in filtered if int(row[0]) <= endTime]
        return filtered[:limit]


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


def _market_data(periods: int = 12) -> pd.DataFrame:
    closes = [100 + index for index in range(periods)]
    return pd.DataFrame(
        {
            "time": pd.date_range("2026-01-01", periods=periods, freq="5min", tz="UTC"),
            "open": closes,
            "high": [value + 3 for value in closes],
            "low": [value - 1 for value in closes],
            "close": closes,
            "volume": [1000] * periods,
        }
    )


def test_backtest_filters_to_configured_date_range_before_signals() -> None:
    strategy = AlwaysLongStrategy()
    engine = BacktestEngine(strategy=strategy, risk_manager=_risk_manager(), initial_capital=10_000)
    start = "2026-01-01T00:20:00Z"
    end = "2026-01-01T00:45:00Z"

    result = engine.run(_market_data(), symbol="ZECUSDT", start_date=start, end_date=end)

    assert result.metrics is not None
    assert result.equity_curve
    assert strategy.observed_last_closed_times
    assert min(strategy.observed_last_closed_times) >= pd.Timestamp(start)
    assert max(strategy.observed_last_closed_times) <= pd.Timestamp(end)


def test_backtest_records_actual_entry_time_in_trade_log() -> None:
    strategy = AlwaysLongStrategy()
    engine = BacktestEngine(strategy=strategy, risk_manager=_risk_manager(), initial_capital=10_000)

    result = engine.run(_market_data(), symbol="ZECUSDT")

    assert result.trades
    assert result.trades[0].entry_time != datetime.min
    assert result.trades[0].entry_time >= pd.Timestamp("2026-01-01T00:00:00Z")


def test_backtest_does_not_open_new_position_on_final_bar() -> None:
    strategy = AlwaysLongStrategy()
    engine = BacktestEngine(strategy=strategy, risk_manager=_risk_manager(), initial_capital=10_000)

    result = engine.run(_market_data(5), symbol="ZECUSDT")

    assert not result.trades


def test_csv_loader_normalizes_and_filters_ohlcv(tmp_path: Path) -> None:
    csv_path = tmp_path / "zec_5m.csv"
    _market_data().to_csv(csv_path, index=False)

    loaded = load_csv_ohlcv(csv_path, start="2026-01-01T00:10:00Z", end="2026-01-01T00:20:00Z")

    assert list(loaded.columns) == ["time", "open", "high", "low", "close", "volume"]
    assert len(loaded) == 3
    assert loaded["time"].min() == pd.Timestamp("2026-01-01T00:10:00Z")
    assert loaded["time"].max() == pd.Timestamp("2026-01-01T00:20:00Z")


def test_binance_historical_loader_normalizes_raw_klines() -> None:
    base = int(datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    rows = [
        [base, "100", "102", "99", "101", "10", base + 1, "0", 1, "0", "0", "0"],
        [base + 300_000, "101", "103", "100", "102", "11", base + 300_001, "0", 1, "0", "0", "0"],
    ]
    loader = BinanceHistoricalDataLoader(FakeBinanceClient(rows), request_limit=100, pause_seconds=0)

    loaded = loader.load_klines(symbol="ZECUSDT", interval="5m")

    assert len(loaded) == 2
    assert loaded.iloc[0]["open"] == 100.0
    assert loaded.iloc[1]["close"] == 102.0
    assert str(loaded.iloc[0]["time"].tzinfo) == "UTC"


def test_multi_symbol_backtest_persists_symbol_and_aggregate_runs(tmp_path: Path) -> None:
    settings = Settings(database_url="sqlite:///:memory:", symbols=["ZECUSDT", "BTCUSDT"])
    factory = create_session_factory(settings.database_url)
    init_db(factory)

    with session_scope(factory) as session:
        report = MultiSymbolBacktestRunner(settings, session).run(
            {
                "ZECUSDT": _market_data(36),
                "BTCUSDT": _market_data(36),
            }
        )
        runs = TradeRepository(session).list_backtest_runs(limit=10)

    json_path = BacktestReportExporter.write_json(report, tmp_path / "report.json")
    html_path = BacktestReportExporter.write_html(report, tmp_path / "report.html")
    payload = json.loads(json_path.read_text(encoding="utf-8"))

    assert report.aggregate.symbol == "MULTI"
    assert len(report.symbols) == 2
    assert {run.symbol for run in runs} == {"ZECUSDT", "BTCUSDT", "MULTI"}
    assert payload["aggregate"]["metrics"]["avg_r_r"] is None
    assert "LWK Futures Backtest Report" in html_path.read_text(encoding="utf-8")
