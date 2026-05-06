from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from app.backtesting.walk_forward import WalkForwardOptimizer, WalkForwardReportExporter
from app.core.config import Settings
from trading_bot.strategies.ema_rsi_vwap import EmaRsiVwapStrategy


def _walk_forward_data(periods: int = 220) -> pd.DataFrame:
    rows = []
    for index in range(periods):
        regime = 1 if index < periods // 2 else -1
        close = 100 + regime * (index % 30) * 0.35 + (index % 7) * 0.08
        rows.append(
            {
                "time": pd.Timestamp("2026-01-01T00:00:00Z") + pd.Timedelta(minutes=5 * index),
                "open": close - 0.1,
                "high": close + 1.4,
                "low": close - 1.1,
                "close": close,
                "volume": 900 + (700 if index % 11 == 0 else 0),
            }
        )
    return pd.DataFrame(rows)


def test_walk_forward_optimizer_builds_out_of_sample_report(tmp_path: Path) -> None:
    settings = Settings(
        symbol="BTCUSDT",
        ema_fast=5,
        ema_slow=12,
        rsi_len=5,
        atr_len=7,
        vol_ma_len=10,
        min_notional=1.0,
        use_atr_position_cap=False,
    )
    optimizer = WalkForwardOptimizer(
        settings,
        train_size=90,
        validation_size=50,
        step_size=40,
        n_trials=2,
        objective="total_return",
        random_seed=7,
    )

    report = optimizer.run(_walk_forward_data(), symbol="btcusdt", timeframe="5m")
    output = WalkForwardReportExporter.write_json(report, tmp_path / "walk_forward.json")
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert report.symbol == "BTCUSDT"
    assert len(report.windows) == 3
    assert report.n_trials == 2
    assert payload["objective"] == "total_return"
    assert payload["aggregate"]["metrics"]["total_trades"] >= 0
    assert "vwap_window" in payload["windows"][0]["best_params"]
    assert payload["windows"][0]["overfit_score"] is not None


def test_walk_forward_optimizer_rejects_short_history() -> None:
    optimizer = WalkForwardOptimizer(
        Settings(),
        train_size=100,
        validation_size=50,
        step_size=25,
        n_trials=1,
    )

    with pytest.raises(ValueError, match="requires at least 150 candles"):
        optimizer.run(_walk_forward_data(149))


def test_strategy_supports_rolling_vwap_window() -> None:
    df = pd.DataFrame(
        {
            "time": pd.date_range("2026-01-01", periods=3, freq="5min", tz="UTC"),
            "open": [10.0, 20.0, 30.0],
            "high": [10.0, 20.0, 30.0],
            "low": [10.0, 20.0, 30.0],
            "close": [10.0, 20.0, 30.0],
            "volume": [1.0, 1.0, 2.0],
        }
    )
    strategy = EmaRsiVwapStrategy(vwap_window=2)

    enriched = strategy.compute_indicators(df)

    assert enriched.iloc[-1]["vwap"] == 80.0 / 3.0
