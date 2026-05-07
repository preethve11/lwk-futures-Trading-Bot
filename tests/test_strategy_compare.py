from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.backtesting.strategy_compare import StrategyComparisonReportExporter, StrategyComparisonRunner
from app.core.config import Settings


def _candles(periods: int = 80) -> pd.DataFrame:
    rows = []
    for index in range(periods):
        close = 100.0 + index * 0.2
        rows.append(
            {
                "time": pd.Timestamp("2026-01-01T00:00:00Z") + pd.Timedelta(minutes=15 * index),
                "open": close - 0.1,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "volume": 1000.0 + index,
            }
        )
    return pd.DataFrame(rows)


def test_strategy_compare_exports_side_by_side_report(tmp_path: Path) -> None:
    settings = Settings(timeframe="15m", use_atr_position_cap=False)
    report = StrategyComparisonRunner(settings).run(
        {("ZECUSDT", "15m"): _candles()},
        baseline="ema_rsi_vwap",
        variants=["ema_rsi_vwap_trend_only"],
    )

    json_path = StrategyComparisonReportExporter.write_json(report, tmp_path / "comparison.json")
    markdown_path = StrategyComparisonReportExporter.write_markdown(report, tmp_path / "comparison.md")

    assert len(report.rows) == 2
    assert json_path.exists()
    assert "Strategy Comparison" in markdown_path.read_text(encoding="utf-8")
