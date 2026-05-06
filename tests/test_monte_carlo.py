from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.analytics.monte_carlo import MonteCarloReportExporter, MonteCarloSimulator, load_trade_pnls_json


def test_monte_carlo_simulator_reports_ruin_distribution(tmp_path: Path) -> None:
    simulator = MonteCarloSimulator(
        initial_capital=1_000.0,
        simulations=5,
        horizon_trades=3,
        ruin_drawdown_pct=20.0,
        random_seed=7,
    )

    report = simulator.run([-100.0])
    output = MonteCarloReportExporter.write_json(report, tmp_path / "monte_carlo.json")
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert report.probability_of_ruin == 1.0
    assert report.final_capital.mean == 700.0
    assert report.total_return_pct.percentile_50 == pytest.approx(-30.0)
    assert report.max_drawdown_pct.percentile_95 == 30.0
    assert len(payload["distributions"]["final_capital"]) == 5
    assert payload["confidence_intervals"]["final_capital"]["p50"] == 700.0


def test_monte_carlo_loads_backtest_report_equity_curve(tmp_path: Path) -> None:
    source = tmp_path / "backtest_report.json"
    source.write_text(
        json.dumps({"aggregate": {"equity_curve": [1_000.0, 1_010.0, 990.0, 1_020.0]}}),
        encoding="utf-8",
    )

    pnls = load_trade_pnls_json(source, initial_capital=1_000.0)

    assert pnls == [10.0, -20.0, 30.0]


def test_monte_carlo_loads_fractional_returns(tmp_path: Path) -> None:
    source = tmp_path / "returns.json"
    source.write_text(json.dumps({"returns": [0.01, -0.02, 0.03]}), encoding="utf-8-sig")

    pnls = load_trade_pnls_json(source, initial_capital=1_000.0)

    assert pnls == [10.0, -20.0, 30.0]


def test_monte_carlo_rejects_missing_trade_input() -> None:
    simulator = MonteCarloSimulator(initial_capital=1_000.0, simulations=10, horizon_trades=5)

    with pytest.raises(ValueError, match="requires at least one trade PnL"):
        simulator.run([])
