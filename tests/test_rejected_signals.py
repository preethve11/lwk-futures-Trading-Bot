from __future__ import annotations

import json
from pathlib import Path

from trading_bot.backtesting.engine import BacktestArtifactExporter, BacktestResult
from trading_bot.strategies.ema_rsi_vwap import EmaRsiVwapStrategy


def test_base_strategy_tracks_rejected_and_executed_signals() -> None:
    strategy = EmaRsiVwapStrategy()

    strategy.record_rejection("volume_too_low")
    strategy.record_rejection("not_a_real_reason")
    strategy.record_executed_signal()

    assert strategy.rejected_signals["volume_too_low"] == 1
    assert strategy.rejected_signals["other"] == 1
    assert strategy.executed_signals == 1
    assert strategy.total_signal_outcomes == 3


def test_rejected_signal_summary_exports_json(tmp_path: Path) -> None:
    result = BacktestResult(
        rejected_signals={"range_too_narrow": 2, "adx_chop_filter": 1},
        executed_signals=1,
    )

    path = BacktestArtifactExporter.write_rejected_signals(result, tmp_path / "rejected_signals.json")
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["total_signals_evaluated"] == 4
    assert payload["rejection_rate"] == 0.75
    assert payload["rejections"]["range_too_narrow"] == 2
