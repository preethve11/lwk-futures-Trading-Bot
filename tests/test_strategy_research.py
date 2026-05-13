from __future__ import annotations

import csv
import json
from pathlib import Path

from app.analytics.strategy_research import StrategyResearchReportExporter, analyze_trade_log, load_trade_log


def _write_trade_log(path: Path) -> None:
    rows = [
        {
            "run": "BTCUSDT_5m",
            "symbol": "BTCUSDT",
            "timeframe": "5m",
            "market_condition": "range_or_mixed_high_volatility",
            "side": "LONG",
            "entry_time": "2026-01-01T00:00:00+00:00",
            "exit_time": "2026-01-01T00:05:00+00:00",
            "duration_minutes": "5",
            "pnl": "-15",
            "pnl_pct": "-0.5",
            "fees": "2",
            "exit_reason": "stop_loss",
        },
        {
            "run": "BTCUSDT_5m",
            "symbol": "BTCUSDT",
            "timeframe": "5m",
            "market_condition": "range_or_mixed_high_volatility",
            "side": "SHORT",
            "entry_time": "2026-01-01T01:00:00+00:00",
            "exit_time": "2026-01-01T01:05:00+00:00",
            "duration_minutes": "5",
            "pnl": "-10",
            "pnl_pct": "-0.3",
            "fees": "2",
            "exit_reason": "stop_loss",
        },
        {
            "run": "ZECUSDT_1h",
            "symbol": "ZECUSDT",
            "timeframe": "1h",
            "market_condition": "uptrend_normal_volatility",
            "side": "LONG",
            "entry_time": "2026-01-02T02:00:00+00:00",
            "exit_time": "2026-01-02T03:00:00+00:00",
            "duration_minutes": "60",
            "pnl": "20",
            "pnl_pct": "1.0",
            "fees": "1",
            "exit_reason": "take_profit",
        },
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_strategy_research_analyzes_trade_distribution(tmp_path: Path) -> None:
    trade_log = tmp_path / "trade_log.csv"
    _write_trade_log(trade_log)

    report = analyze_trade_log(trade_log)

    assert report.overview["total_trades"] == 3
    assert report.overview["total_pnl"] == -5.0
    assert report.by_run["BTCUSDT_5m"]["profit_factor"] == 0.0
    assert report.by_timeframe["5m"]["expectancy"] == -12.5
    assert report.question_analysis["worst_run"]["run"] == "BTCUSDT_5m"
    assert report.question_analysis["why_btcusdt_5m_worse"]["metrics"]["total_trades"] == 2
    assert report.timing_analysis["best_day_of_week"] is not None
    assert report.crowding_analysis["crowding_rejections"] == 0
    assert report.correlated_exposure_analysis["max_symbol_positive_pnl_share"] == 1.0
    assert any(issue.area == "BTCUSDT_5m" for issue in report.issues)


def test_strategy_research_exports_json_and_markdown(tmp_path: Path) -> None:
    trade_log = tmp_path / "trade_log.csv"
    _write_trade_log(trade_log)
    report = analyze_trade_log(trade_log)

    json_path = StrategyResearchReportExporter.write_json(report, tmp_path / "research.json")
    markdown_path = StrategyResearchReportExporter.write_markdown(report, tmp_path / "research.md")

    payload = json.loads(json_path.read_text(encoding="utf-8"))

    assert payload["overview"]["total_trades"] == 3
    assert "Strategy Research Diagnostics" in markdown_path.read_text(encoding="utf-8")


def test_load_trade_log_rejects_empty_file(tmp_path: Path) -> None:
    trade_log = tmp_path / "trade_log.csv"
    trade_log.write_text("run,symbol,timeframe,pnl\n", encoding="utf-8")

    try:
        load_trade_log(trade_log)
    except ValueError as exc:
        assert "empty" in str(exc)
    else:
        raise AssertionError("expected empty trade log to be rejected")
