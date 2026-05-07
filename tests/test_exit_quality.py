from __future__ import annotations

import csv
from pathlib import Path

from app.analytics.strategy_research import analyze_trade_log


def test_strategy_research_reports_exit_quality(tmp_path: Path) -> None:
    trade_log = tmp_path / "trade_log.csv"
    rows = [
        {
            "run": "ZECUSDT_1h",
            "symbol": "ZECUSDT",
            "timeframe": "1h",
            "market_condition": "trend",
            "side": "LONG",
            "entry_price": "100",
            "exit_price": "94.9",
            "intended_stop_loss": "95",
            "intended_take_profit": "105",
            "exit_slippage": "-0.1",
            "entry_time": "2026-01-01T00:00:00+00:00",
            "exit_time": "2026-01-01T01:00:00+00:00",
            "duration_minutes": "60",
            "pnl": "-10",
            "pnl_pct": "-1",
            "fees": "1",
            "exit_reason": "stop_loss",
            "premature_stop": "true",
            "target_approach_pct": "35",
        },
        {
            "run": "ZECUSDT_1h",
            "symbol": "ZECUSDT",
            "timeframe": "1h",
            "market_condition": "trend",
            "side": "LONG",
            "entry_price": "100",
            "exit_price": "105.1",
            "intended_stop_loss": "95",
            "intended_take_profit": "105",
            "exit_slippage": "0.1",
            "entry_time": "2026-01-01T02:00:00+00:00",
            "exit_time": "2026-01-01T03:00:00+00:00",
            "duration_minutes": "60",
            "pnl": "12",
            "pnl_pct": "1.2",
            "fees": "1",
            "exit_reason": "take_profit",
            "premature_stop": "false",
            "target_approach_pct": "100",
        },
    ]
    with trade_log.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    report = analyze_trade_log(trade_log)

    assert report.exit_quality_analysis["stops_hit_pct"] == 0.5
    assert report.exit_quality_analysis["targets_hit_pct"] == 0.5
    assert report.exit_quality_analysis["premature_stops_pct"] == 1.0
    assert report.exit_quality_analysis["avg_sl_slippage_pct"] is not None
