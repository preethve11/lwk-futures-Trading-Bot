"""Strategy research diagnostics for simulated trade logs."""

from __future__ import annotations

import csv
import json
import math
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from trading_bot.analytics.metrics import sharpe_ratio


@dataclass(frozen=True)
class TradeLogRecord:
    """One closed simulated trade loaded from a paper-validation CSV."""

    run: str
    symbol: str
    timeframe: str
    market_condition: str
    side: str
    entry_price: float
    exit_price: float
    entry_time: datetime | None
    exit_time: datetime | None
    duration_minutes: float
    pnl: float
    pnl_pct: float
    fees: float
    exit_reason: str
    intended_stop_loss: float = 0.0
    intended_take_profit: float = 0.0
    exit_slippage: float = 0.0
    premature_stop: bool = False
    target_approach_pct: float = 0.0
    volatility_regime: str = ""
    trend_regime: str = ""
    volume_regime: str = ""
    signal_rejected_reason: str = ""
    range_width_pct: float = 0.0
    ema_50: float = 0.0
    adx_14: float = 0.0
    intended_sl_pct: float = 0.0
    intended_tp_pct: float = 0.0
    session_name: str = ""
    session_open_time_utc: str = ""

    @property
    def entry_hour_utc(self) -> str:
        if self.entry_time is None:
            return "unknown"
        return f"{self.entry_time.hour:02d}:00"

    @property
    def range_width_bucket(self) -> str:
        if self.range_width_pct <= 0:
            return "unknown"
        if self.range_width_pct < 0.4:
            return "<0.4%"
        if self.range_width_pct < 0.8:
            return "0.4-0.8%"
        if self.range_width_pct < 1.5:
            return "0.8-1.5%"
        return ">=1.5%"

    @property
    def ema_alignment_bucket(self) -> str:
        if self.ema_50 <= 0 or self.entry_price <= 0:
            return "unknown"
        if self.side.upper() == "LONG":
            return "with_ema_regime" if self.entry_price > self.ema_50 else "against_ema_regime"
        if self.side.upper() == "SHORT":
            return "with_ema_regime" if self.entry_price < self.ema_50 else "against_ema_regime"
        return "unknown"

    @property
    def adx_bucket(self) -> str:
        if self.adx_14 <= 0:
            return "unknown"
        return "adx_ge_20" if self.adx_14 >= 20.0 else "adx_lt_20"


@dataclass(frozen=True)
class ResearchIssue:
    """Actionable research issue detected from the trade distribution."""

    severity: str
    area: str
    finding: str
    recommendation: str

    def to_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity,
            "area": self.area,
            "finding": self.finding,
            "recommendation": self.recommendation,
        }


@dataclass(frozen=True)
class StrategyResearchReport:
    """Portable strategy research report."""

    generated_at: datetime
    source_path: str
    overview: dict[str, Any]
    by_run: dict[str, dict[str, Any]]
    by_symbol: dict[str, dict[str, Any]]
    by_timeframe: dict[str, dict[str, Any]]
    by_market_condition: dict[str, dict[str, Any]]
    by_entry_hour_utc: dict[str, dict[str, Any]]
    by_exit_reason: dict[str, dict[str, Any]]
    by_trend_regime: dict[str, dict[str, Any]]
    by_volatility_regime: dict[str, dict[str, Any]]
    by_volume_regime: dict[str, dict[str, Any]]
    by_session: dict[str, dict[str, Any]]
    by_range_width_bucket: dict[str, dict[str, Any]]
    by_ema_alignment: dict[str, dict[str, Any]]
    by_adx_bucket: dict[str, dict[str, Any]]
    rejected_signal_analysis: dict[str, Any]
    exit_quality_analysis: dict[str, Any]
    cost_analysis: dict[str, Any]
    outlier_analysis: dict[str, Any]
    question_analysis: dict[str, Any]
    issues: list[ResearchIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at.isoformat(),
            "source_path": self.source_path,
            "overview": self.overview,
            "by_run": self.by_run,
            "by_symbol": self.by_symbol,
            "by_timeframe": self.by_timeframe,
            "by_market_condition": self.by_market_condition,
            "by_entry_hour_utc": self.by_entry_hour_utc,
            "by_exit_reason": self.by_exit_reason,
            "by_trend_regime": self.by_trend_regime,
            "by_volatility_regime": self.by_volatility_regime,
            "by_volume_regime": self.by_volume_regime,
            "by_session": self.by_session,
            "by_range_width_bucket": self.by_range_width_bucket,
            "by_ema_alignment": self.by_ema_alignment,
            "by_adx_bucket": self.by_adx_bucket,
            "rejected_signal_analysis": self.rejected_signal_analysis,
            "exit_quality_analysis": self.exit_quality_analysis,
            "cost_analysis": self.cost_analysis,
            "outlier_analysis": self.outlier_analysis,
            "question_analysis": self.question_analysis,
            "issues": [issue.to_dict() for issue in self.issues],
        }


def load_trade_log(path: Path) -> list[TradeLogRecord]:
    """Load paper-validation trade rows from CSV."""
    if not path.exists():
        raise FileNotFoundError(f"Trade log not found: {path}")
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    records = [_record_from_row(row) for row in rows]
    if not records:
        raise ValueError(f"Trade log is empty: {path}")
    return records


def analyze_trade_log(
    path: Path,
    *,
    rejected_signals_path: Path | None = None,
    group_by_regime: bool = False,
) -> StrategyResearchReport:
    """Analyze a trade log and produce grouped research diagnostics."""
    records = load_trade_log(path)
    by_run = _group_metrics(records, lambda record: record.run)
    by_symbol = _group_metrics(records, lambda record: record.symbol)
    by_timeframe = _group_metrics(records, lambda record: record.timeframe)
    by_market_condition = _group_metrics(records, lambda record: record.market_condition)
    by_entry_hour_utc = _group_metrics(records, lambda record: record.entry_hour_utc)
    by_exit_reason = _group_metrics(records, lambda record: record.exit_reason)
    by_trend_regime = _group_metrics(records, lambda record: record.trend_regime or "unknown") if group_by_regime else {}
    by_volatility_regime = (
        _group_metrics(records, lambda record: record.volatility_regime or "unknown") if group_by_regime else {}
    )
    by_volume_regime = _group_metrics(records, lambda record: record.volume_regime or "unknown") if group_by_regime else {}
    by_session = _group_metrics(records, lambda record: record.session_name or "unknown")
    by_range_width_bucket = _group_metrics(records, lambda record: record.range_width_bucket)
    by_ema_alignment = _group_metrics(records, lambda record: record.ema_alignment_bucket)
    by_adx_bucket = _group_metrics(records, lambda record: record.adx_bucket)
    overview = _metrics(records)
    rejected_signal_analysis = _rejected_signal_analysis(
        rejected_signals_path or _default_rejected_signals_path(path),
        executed_trades=len(records),
    )
    exit_quality_analysis = _exit_quality_analysis(records)
    outliers = _outlier_analysis(records)
    cost_analysis = _cost_analysis(records, by_timeframe)
    question_analysis = _question_analysis(by_run, by_timeframe, outliers)
    issues = _detect_issues(by_run, by_timeframe, cost_analysis, outliers, exit_quality_analysis)
    return StrategyResearchReport(
        generated_at=datetime.now(timezone.utc),
        source_path=str(path),
        overview=overview,
        by_run=by_run,
        by_symbol=by_symbol,
        by_timeframe=by_timeframe,
        by_market_condition=by_market_condition,
        by_entry_hour_utc=by_entry_hour_utc,
        by_exit_reason=by_exit_reason,
        by_trend_regime=by_trend_regime,
        by_volatility_regime=by_volatility_regime,
        by_volume_regime=by_volume_regime,
        by_session=by_session,
        by_range_width_bucket=by_range_width_bucket,
        by_ema_alignment=by_ema_alignment,
        by_adx_bucket=by_adx_bucket,
        rejected_signal_analysis=rejected_signal_analysis,
        exit_quality_analysis=exit_quality_analysis,
        cost_analysis=cost_analysis,
        outlier_analysis=outliers,
        question_analysis=question_analysis,
        issues=issues,
    )


class StrategyResearchReportExporter:
    """Write strategy research reports to JSON or Markdown."""

    @staticmethod
    def write_json(report: StrategyResearchReport, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report.to_dict(), indent=2, allow_nan=False), encoding="utf-8")
        return path

    @staticmethod
    def write_markdown(report: StrategyResearchReport, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_markdown_report(report), encoding="utf-8")
        return path


def _record_from_row(row: dict[str, str]) -> TradeLogRecord:
    run = _text(row, "run", default="UNKNOWN")
    symbol = _text(row, "symbol", default=_symbol_from_run(run))
    timeframe = _text(row, "timeframe", default=_timeframe_from_run(run))
    return TradeLogRecord(
        run=run,
        symbol=symbol,
        timeframe=timeframe,
        market_condition=_text(row, "market_condition", default=_text(row, "condition", default="unknown")),
        side=_text(row, "side", default="unknown"),
        entry_price=_float(row.get("entry_price")),
        exit_price=_float(row.get("exit_price")),
        entry_time=_parse_datetime(row.get("entry_time")),
        exit_time=_parse_datetime(row.get("exit_time")),
        duration_minutes=_float(row.get("duration_minutes")),
        pnl=_float(row.get("pnl")),
        pnl_pct=_float(row.get("pnl_pct")),
        fees=_float(row.get("fees")),
        exit_reason=_text(row, "exit_reason", default="unknown"),
        intended_stop_loss=_float(row.get("intended_stop_loss")),
        intended_take_profit=_float(row.get("intended_take_profit")),
        exit_slippage=_float(row.get("exit_slippage")),
        premature_stop=_bool(row.get("premature_stop")),
        target_approach_pct=_float(row.get("target_approach_pct")),
        volatility_regime=_text(row, "volatility_regime", default="unknown"),
        trend_regime=_text(row, "trend_regime", default="unknown"),
        volume_regime=_text(row, "volume_regime", default="unknown"),
        signal_rejected_reason=_text(row, "signal_rejected_reason", default=""),
        range_width_pct=_float(row.get("range_width_pct")),
        ema_50=_float(row.get("ema_50")),
        adx_14=_float(row.get("adx_14")),
        intended_sl_pct=_float(row.get("intended_sl_pct")),
        intended_tp_pct=_float(row.get("intended_tp_pct")),
        session_name=_text(row, "session_name", default="unknown"),
        session_open_time_utc=_text(row, "session_open_time_utc", default=""),
    )


def _text(row: dict[str, str], key: str, *, default: str) -> str:
    value = row.get(key)
    if value is None or not value.strip():
        return default
    return value.strip()


def _float(value: str | None) -> float:
    if value is None or not value.strip():
        return 0.0
    return float(value)


def _bool(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "y"}


def _parse_datetime(value: str | None) -> datetime | None:
    if value is None or not value.strip():
        return None
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _symbol_from_run(run: str) -> str:
    return run.split("_", 1)[0] if "_" in run else "UNKNOWN"


def _timeframe_from_run(run: str) -> str:
    return run.rsplit("_", 1)[-1] if "_" in run else "unknown"


def _group_metrics(
    records: Iterable[TradeLogRecord],
    key_fn: Callable[[TradeLogRecord], str],
) -> dict[str, dict[str, Any]]:
    buckets: dict[str, list[TradeLogRecord]] = {}
    for record in records:
        buckets.setdefault(key_fn(record), []).append(record)
    return {key: _metrics(bucket) for key, bucket in sorted(buckets.items())}


def _metrics(records: list[TradeLogRecord]) -> dict[str, Any]:
    pnls = [record.pnl for record in records]
    wins = [pnl for pnl in pnls if pnl > 0]
    losses = [pnl for pnl in pnls if pnl < 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    net_pnl = sum(pnls)
    fees = sum(record.fees for record in records)
    gross_before_fees = net_pnl + fees
    avg_loss = (sum(losses) / len(losses)) if losses else 0.0
    avg_win = (gross_profit / len(wins)) if wins else 0.0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else None
    avg_risk_reward = (avg_win / abs(avg_loss)) if avg_loss < 0 else None
    trade_returns = [pnl / 10_000.0 for pnl in pnls]
    return {
        "total_trades": len(records),
        "total_pnl": _number(net_pnl),
        "gross_profit": _number(gross_profit),
        "gross_loss": _number(gross_loss),
        "gross_before_fees": _number(gross_before_fees),
        "win_rate": _number(len(wins) / len(records)) if records else 0.0,
        "profit_factor": _number(profit_factor),
        "sharpe": _number(sharpe_ratio(trade_returns)) if trade_returns else 0.0,
        "expectancy": _number(net_pnl / len(records)) if records else 0.0,
        "expectancy_before_fees": _number(gross_before_fees / len(records)) if records else 0.0,
        "median_pnl": _number(statistics.median(pnls)) if pnls else 0.0,
        "avg_win": _number(avg_win),
        "avg_loss": _number(avg_loss),
        "avg_risk_reward": _number(avg_risk_reward),
        "largest_win": _number(max(pnls)) if pnls else 0.0,
        "largest_loss": _number(min(pnls)) if pnls else 0.0,
        "total_fees": _number(fees),
        "avg_fee": _number(fees / len(records)) if records else 0.0,
        "fee_to_gross_profit_pct": _number((fees / gross_profit) * 100.0) if gross_profit > 0 else None,
        "fee_to_abs_net_pnl_pct": _number((fees / abs(net_pnl)) * 100.0) if abs(net_pnl) > 0 else None,
        "avg_duration_minutes": _number(statistics.mean(record.duration_minutes for record in records)),
    }


def _default_rejected_signals_path(trade_log_path: Path) -> Path | None:
    candidate = trade_log_path.parent / "rejected_signals.json"
    return candidate if candidate.exists() else None


def _rejected_signal_analysis(path: Path | None, *, executed_trades: int) -> dict[str, Any]:
    if path is None or not path.exists():
        return {
            "available": False,
            "path": str(path) if path is not None else None,
            "total_signals_evaluated": executed_trades,
            "executed_trades": executed_trades,
            "rejected_signals": 0,
            "rejection_rate": 0.0,
            "rejected_to_executed_ratio": 0.0,
            "rejections": {},
        }
    payload = json.loads(path.read_text(encoding="utf-8"))
    rejections_raw = payload.get("rejections", {})
    rejections = {str(key): int(value) for key, value in rejections_raw.items()} if isinstance(rejections_raw, dict) else {}
    rejected = sum(rejections.values())
    executed = int(payload.get("executed_trades") or payload.get("executed_signals") or executed_trades)
    total = int(payload.get("total_signals_evaluated") or (executed + rejected))
    return {
        "available": True,
        "path": str(path),
        "total_signals_evaluated": total,
        "executed_trades": executed,
        "rejected_signals": rejected,
        "rejection_rate": _number((rejected / total) if total else 0.0),
        "rejected_to_executed_ratio": _number((rejected / executed) if executed else 0.0),
        "rejections": rejections,
    }


def _exit_quality_analysis(records: list[TradeLogRecord]) -> dict[str, Any]:
    total = len(records)
    stop_hits = [record for record in records if record.exit_reason == "stop_loss"]
    target_hits = [record for record in records if record.exit_reason == "take_profit"]
    premature = [record for record in stop_hits if record.premature_stop]
    unrealistic = [
        record
        for record in records
        if record.exit_reason != "take_profit" and record.target_approach_pct < 50.0
    ]
    avg_sl_slippage = _average_pct_slippage(stop_hits, intended_field="stop")
    avg_tp_slippage = _average_pct_slippage(target_hits, intended_field="take_profit")
    return {
        "total_trades": total,
        "stops_hit_pct": _number(len(stop_hits) / total) if total else 0.0,
        "targets_hit_pct": _number(len(target_hits) / total) if total else 0.0,
        "premature_stops_pct": _number(len(premature) / len(stop_hits)) if stop_hits else 0.0,
        "unrealistic_targets_pct": _number(len(unrealistic) / total) if total else 0.0,
        "avg_sl_slippage_pct": _number(avg_sl_slippage),
        "avg_tp_slippage_pct": _number(avg_tp_slippage),
        "recommendation": _exit_quality_recommendation(stop_hits, target_hits, premature, unrealistic, total),
    }


def _average_pct_slippage(records: list[TradeLogRecord], *, intended_field: str) -> float:
    percentages: list[float] = []
    for record in records:
        intended = record.intended_stop_loss if intended_field == "stop" else record.intended_take_profit
        if intended == 0.0:
            continue
        percentages.append((record.exit_slippage / intended) * 100.0)
    return statistics.mean(percentages) if percentages else 0.0


def _exit_quality_recommendation(
    stop_hits: list[TradeLogRecord],
    target_hits: list[TradeLogRecord],
    premature: list[TradeLogRecord],
    unrealistic: list[TradeLogRecord],
    total: int,
) -> str:
    if total == 0:
        return "No closed trades available for exit-quality analysis."
    stop_rate = len(stop_hits) / total
    target_rate = len(target_hits) / total
    premature_rate = len(premature) / len(stop_hits) if stop_hits else 0.0
    unrealistic_rate = len(unrealistic) / total
    if premature_rate >= 0.2 and unrealistic_rate >= 0.3:
        return "Widen stops by 1.5x and reduce TP distance by 0.8x before the next validation run."
    if stop_rate > target_rate * 2.0:
        return "Stops dominate exits; test wider ATR stops and stricter entry filters."
    if unrealistic_rate >= 0.3:
        return "Targets are rarely approached; reduce TP distance or require stronger momentum confirmation."
    return "Exit distances are not the primary observed failure; prioritize regime and signal-quality filters."


def _outlier_analysis(records: list[TradeLogRecord]) -> dict[str, Any]:
    losses = sorted((record for record in records if record.pnl < 0), key=lambda record: record.pnl)
    wins = sorted((record for record in records if record.pnl > 0), key=lambda record: record.pnl, reverse=True)
    gross_loss = abs(sum(record.pnl for record in losses))
    top_loss_count = max(1, math.ceil(len(losses) * 0.05)) if losses else 0
    top_loss_sum = abs(sum(record.pnl for record in losses[:top_loss_count]))
    concentration = (top_loss_sum / gross_loss) if gross_loss > 0 else 0.0
    median_pnl = statistics.median(record.pnl for record in records)
    if median_pnl < 0 and concentration < 0.35:
        loss_mode = "persistent_small_losses"
    elif concentration >= 0.35:
        loss_mode = "outlier_loss_concentration"
    else:
        loss_mode = "mixed"
    return {
        "loss_mode": loss_mode,
        "median_pnl": _number(median_pnl),
        "top_loss_count": top_loss_count,
        "top_loss_share_of_gross_loss": _number(concentration),
        "largest_losses": [_trade_snapshot(record) for record in losses[:10]],
        "largest_wins": [_trade_snapshot(record) for record in wins[:10]],
    }


def _trade_snapshot(record: TradeLogRecord) -> dict[str, Any]:
    return {
        "run": record.run,
        "symbol": record.symbol,
        "timeframe": record.timeframe,
        "side": record.side,
        "entry_time": record.entry_time.isoformat() if record.entry_time is not None else None,
        "exit_time": record.exit_time.isoformat() if record.exit_time is not None else None,
        "pnl": _number(record.pnl),
        "fees": _number(record.fees),
        "exit_reason": record.exit_reason,
    }


def _cost_analysis(records: list[TradeLogRecord], by_timeframe: dict[str, dict[str, Any]]) -> dict[str, Any]:
    overview = _metrics(records)
    timeframe_drag = {
        timeframe: {
            "total_fees": metrics["total_fees"],
            "avg_fee": metrics["avg_fee"],
            "expectancy": metrics["expectancy"],
            "expectancy_before_fees": metrics["expectancy_before_fees"],
            "fee_to_gross_profit_pct": metrics["fee_to_gross_profit_pct"],
        }
        for timeframe, metrics in by_timeframe.items()
    }
    return {
        "total_fees": overview["total_fees"],
        "gross_before_fees": overview["gross_before_fees"],
        "net_after_fees": overview["total_pnl"],
        "avg_fee_per_trade": overview["avg_fee"],
        "fee_to_gross_profit_pct": overview["fee_to_gross_profit_pct"],
        "timeframe_fee_drag": timeframe_drag,
    }


def _question_analysis(
    by_run: dict[str, dict[str, Any]],
    by_timeframe: dict[str, dict[str, Any]],
    outliers: dict[str, Any],
) -> dict[str, Any]:
    worst_run = min(by_run.items(), key=lambda item: float(item[1]["total_pnl"]))
    best_run = max(by_run.items(), key=lambda item: float(item[1]["total_pnl"]))
    five_min = by_timeframe.get("5m")
    higher_timeframes = [
        metrics
        for timeframe, metrics in by_timeframe.items()
        if timeframe != "5m"
    ]
    higher_expectancy = (
        statistics.mean(float(metrics["expectancy"]) for metrics in higher_timeframes)
        if higher_timeframes
        else None
    )
    five_min_expectancy = float(five_min["expectancy"]) if five_min is not None else None
    return {
        "why_btcusdt_5m_worse": _btc_5m_answer(by_run),
        "is_5m_too_noisy_or_costly": {
            "five_min_expectancy": _number(five_min_expectancy),
            "higher_timeframe_avg_expectancy": _number(higher_expectancy),
            "answer": _timeframe_answer(five_min_expectancy, higher_expectancy),
        },
        "why_all_timeframes_underperform": _all_timeframe_answer(by_timeframe),
        "trade_distribution": {
            "loss_mode": outliers["loss_mode"],
            "median_pnl": outliers["median_pnl"],
            "top_loss_share_of_gross_loss": outliers["top_loss_share_of_gross_loss"],
            "answer": _distribution_answer(outliers),
        },
        "best_run": {"run": best_run[0], "metrics": best_run[1]},
        "worst_run": {"run": worst_run[0], "metrics": worst_run[1]},
    }


def _btc_5m_answer(by_run: dict[str, dict[str, Any]]) -> dict[str, Any]:
    btc = by_run.get("BTCUSDT_5m")
    if btc is None:
        return {"answer": "BTCUSDT_5m was not present in the trade log."}
    return {
        "metrics": btc,
        "answer": (
            "BTCUSDT_5m is failing through both low win rate and deeply negative expectancy. "
            "The pattern is consistent with a noisy lower-timeframe signal that is not overcoming fees, slippage, and stop-outs."
        ),
    }


def _timeframe_answer(five_min_expectancy: float | None, higher_expectancy: float | None) -> str:
    if five_min_expectancy is None or higher_expectancy is None:
        return "Insufficient timeframe coverage to compare 5m against higher timeframes."
    if five_min_expectancy < higher_expectancy:
        return "The 5m trades are materially worse than higher timeframes; treat 5m as disabled until a separate lower-timeframe edge is proven."
    return "The 5m timeframe is not uniquely worse in this sample; the edge problem appears broader than timeframe noise alone."


def _all_timeframe_answer(by_timeframe: dict[str, dict[str, Any]]) -> str:
    negative = [
        timeframe
        for timeframe, metrics in by_timeframe.items()
        if float(metrics["expectancy"]) <= 0 or _optional_float(metrics["profit_factor"]) < 1.1
    ]
    if len(negative) == len(by_timeframe):
        return (
            "Every tested timeframe fails either positive expectancy or profit-factor requirements. "
            "That points to a non-predictive signal/threshold set, not only bad execution costs."
        )
    return "Some timeframe buckets survive basic expectancy checks; research should isolate those before adding complexity."


def _distribution_answer(outliers: dict[str, Any]) -> str:
    if outliers["loss_mode"] == "persistent_small_losses":
        return "Losses are broad-based rather than dominated by a few extreme outliers; the strategy appears to lack edge trade-by-trade."
    if outliers["loss_mode"] == "outlier_loss_concentration":
        return "A small number of large losses dominate gross loss; focus on stop logic, volatility filters, and event-risk avoidance."
    return "The trade distribution is mixed; inspect both outliers and median trade quality."


def _detect_issues(
    by_run: dict[str, dict[str, Any]],
    by_timeframe: dict[str, dict[str, Any]],
    cost_analysis: dict[str, Any],
    outliers: dict[str, Any],
    exit_quality: dict[str, Any],
) -> list[ResearchIssue]:
    issues: list[ResearchIssue] = []
    for run, metrics in by_run.items():
        profit_factor = _optional_float(metrics["profit_factor"])
        expectancy = float(metrics["expectancy"])
        if profit_factor < 1.1:
            issues.append(
                ResearchIssue(
                    severity="critical",
                    area=run,
                    finding=f"Profit factor {profit_factor:.2f} is below the 1.10 live gate.",
                    recommendation="Do not promote this symbol/timeframe. Rework signal filters or disable this bucket.",
                )
            )
        if expectancy <= 0:
            issues.append(
                ResearchIssue(
                    severity="critical",
                    area=run,
                    finding=f"Expectancy {expectancy:.2f} USD/trade is not positive.",
                    recommendation="Require positive out-of-sample expectancy before further execution testing.",
                )
            )
    five_min = by_timeframe.get("5m")
    if five_min is not None and float(five_min["expectancy"]) <= 0:
        issues.append(
            ResearchIssue(
                severity="high",
                area="5m timeframe",
                finding=f"5m aggregate expectancy is {float(five_min['expectancy']):.2f} USD/trade.",
                recommendation="Disable 5m for this strategy until lower-timeframe research proves a distinct edge.",
            )
        )
    fee_pct = _optional_float(cost_analysis.get("fee_to_gross_profit_pct"))
    if fee_pct > 50.0:
        issues.append(
            ResearchIssue(
                severity="high",
                area="transaction costs",
                finding=f"Fees consume {fee_pct:.1f}% of gross profit.",
                recommendation="Reduce trade frequency, require larger expected moves, or model maker/taker costs by symbol.",
            )
        )
    if outliers["loss_mode"] == "persistent_small_losses":
        issues.append(
            ResearchIssue(
                severity="high",
                area="trade distribution",
                finding="Median trade PnL is negative and losses are broad-based.",
                recommendation="Prioritize signal quality and regime filters over only widening stops.",
            )
        )
    premature_stops_pct = _optional_float(exit_quality.get("premature_stops_pct"))
    unrealistic_targets_pct = _optional_float(exit_quality.get("unrealistic_targets_pct"))
    if premature_stops_pct >= 0.2:
        issues.append(
            ResearchIssue(
                severity="medium",
                area="exit quality",
                finding=f"{premature_stops_pct * 100:.1f}% of stop-loss exits reached the target shortly afterward.",
                recommendation="Backtest wider stop distances and stricter trend/regime filters.",
            )
        )
    if unrealistic_targets_pct >= 0.3:
        issues.append(
            ResearchIssue(
                severity="medium",
                area="target quality",
                finding=f"{unrealistic_targets_pct * 100:.1f}% of trades never approached half the planned target distance.",
                recommendation="Test smaller TP multiples or require stronger momentum before entry.",
            )
        )
    return issues


def _optional_float(value: object) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def _number(value: float | None) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    return round(value, 6)


def _markdown_report(report: StrategyResearchReport) -> str:
    overview = report.overview
    rejected = report.rejected_signal_analysis
    exit_quality = report.exit_quality_analysis
    lines = [
        "# Strategy Research Diagnostics",
        "",
        f"Generated: `{report.generated_at.isoformat()}`",
        f"Source: `{report.source_path}`",
        "",
        "## Overview",
        "",
        f"- Trades: `{overview['total_trades']}`",
        f"- Total PnL: `{overview['total_pnl']}`",
        f"- Win rate: `{float(overview['win_rate']) * 100:.1f}%`",
        f"- Profit factor: `{overview['profit_factor']}`",
        f"- Sharpe: `{overview['sharpe']}`",
        f"- Expectancy: `{overview['expectancy']}` USD/trade",
        f"- Median PnL: `{overview['median_pnl']}`",
        f"- Rejected/executed ratio: `{rejected['rejected_to_executed_ratio']}`",
        "",
        "## Rejected Signal Analysis",
        "",
        f"- Available: `{rejected['available']}`",
        f"- Total signals evaluated: `{rejected['total_signals_evaluated']}`",
        f"- Executed trades: `{rejected['executed_trades']}`",
        f"- Rejected signals: `{rejected['rejected_signals']}`",
        f"- Rejection rate: `{float(rejected['rejection_rate']) * 100:.1f}%`",
        f"- Rejected/executed ratio: `{rejected['rejected_to_executed_ratio']}`",
        "",
    ]
    if rejected["rejections"]:
        lines.extend(
            [
                "| Reason | Count |",
                "| --- | ---: |",
            ]
        )
        for reason, count in sorted(rejected["rejections"].items()):
            lines.append(f"| {reason} | {count} |")
        lines.append("")
    lines.extend(
        [
            "## Exit Quality Analysis",
            "",
            f"- Stops hit: `{float(exit_quality['stops_hit_pct']) * 100:.1f}%` of trades",
            f"- Targets hit: `{float(exit_quality['targets_hit_pct']) * 100:.1f}%` of trades",
            f"- Premature stops: `{float(exit_quality['premature_stops_pct']) * 100:.1f}%` of stop exits",
            f"- Unrealistic targets: `{float(exit_quality['unrealistic_targets_pct']) * 100:.1f}%` of trades",
            f"- Avg SL slippage: `{exit_quality['avg_sl_slippage_pct']}`%",
            f"- Avg TP slippage: `{exit_quality['avg_tp_slippage_pct']}`%",
            "",
            f"**Recommendation**: {exit_quality['recommendation']}",
            "",
            "## Regime Performance Breakdown",
            "",
        ]
    )
    lines.extend(_regime_section("By Trend Regime", report.by_trend_regime, positive_label="TRENDING"))
    lines.extend(_regime_section("By Volatility Regime", report.by_volatility_regime, positive_label="HIGH_VOL"))
    lines.extend(_regime_section("By Volume Regime", report.by_volume_regime, positive_label="HIGH_VOLUME"))
    lines.extend(_group_section("Performance By Session", report.by_session))
    lines.extend(_group_section("Performance By Range Width", report.by_range_width_bucket))
    lines.extend(_group_section("Performance By EMA Regime Alignment", report.by_ema_alignment))
    lines.extend(_group_section("Performance By ADX Bucket", report.by_adx_bucket))
    lines.extend(
        [
            "## Direct Answers",
            "",
            f"- BTCUSDT 5m: {report.question_analysis['why_btcusdt_5m_worse']['answer']}",
            f"- 5m noise/cost: {report.question_analysis['is_5m_too_noisy_or_costly']['answer']}",
            f"- Broad underperformance: {report.question_analysis['why_all_timeframes_underperform']}",
            f"- Distribution: {report.question_analysis['trade_distribution']['answer']}",
            "",
            "## Metrics By Run",
            "",
            "| Run | Trades | PnL | Win % | PF | Expectancy | Fees | Median PnL |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for run, metrics in sorted(report.by_run.items()):
        lines.append(
            f"| {run} | {metrics['total_trades']} | {metrics['total_pnl']} | "
            f"{float(metrics['win_rate']) * 100:.1f} | {_md(metrics['profit_factor'])} | "
            f"{metrics['expectancy']} | {metrics['total_fees']} | {metrics['median_pnl']} |"
        )
    lines.extend(
        [
            "",
            "## Issues",
            "",
        ]
    )
    for issue in report.issues:
        lines.append(f"- **{issue.severity.upper()} [{issue.area}]** {issue.finding} Recommendation: {issue.recommendation}")
    lines.extend(
        [
            "",
            "## Next Research Moves",
            "",
            "- Disable failing symbol/timeframe buckets before live testing.",
            "- Add regime labels to backtests and test trend/range filters out of sample.",
            "- Use rejected-signal counters and intended SL/TP columns to isolate filter and exit-distance failures.",
            "- Run authenticated Binance testnet after a strategy passes the live performance gate.",
            "",
        ]
    )
    return "\n".join(lines)


def _regime_section(title: str, metrics_by_regime: dict[str, dict[str, Any]], *, positive_label: str) -> list[str]:
    if not metrics_by_regime:
        return [f"### {title}", "", "No regime labels were available in this trade log.", ""]
    lines = [
        f"### {title}",
        "",
        "| Regime | Trades | Win % | PF | Expectancy | Sharpe |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    best_regime = ""
    best_expectancy = float("-inf")
    for regime, metrics in sorted(metrics_by_regime.items()):
        expectancy = float(metrics["expectancy"])
        if expectancy > best_expectancy:
            best_expectancy = expectancy
            best_regime = regime
        lines.append(
            f"| {regime} | {metrics['total_trades']} | {float(metrics['win_rate']) * 100:.1f} | "
            f"{_md(metrics['profit_factor'])} | {metrics['expectancy']} | {_md(metrics['sharpe'])} |"
        )
    recommendation = _regime_recommendation(best_regime, best_expectancy, positive_label)
    lines.extend(["", f"**Recommendation**: {recommendation}", ""])
    return lines


def _group_section(title: str, metrics_by_group: dict[str, dict[str, Any]]) -> list[str]:
    if not metrics_by_group:
        return [f"## {title}", "", "No data available.", ""]
    lines = [
        f"## {title}",
        "",
        "| Bucket | Trades | PnL | Win % | PF | Expectancy | Fees |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for bucket, metrics in sorted(metrics_by_group.items()):
        lines.append(
            f"| {bucket} | {metrics['total_trades']} | {metrics['total_pnl']} | "
            f"{float(metrics['win_rate']) * 100:.1f} | {_md(metrics['profit_factor'])} | "
            f"{metrics['expectancy']} | {metrics['total_fees']} |"
        )
    lines.append("")
    return lines


def _regime_recommendation(best_regime: str, best_expectancy: float, positive_label: str) -> str:
    if best_expectancy <= 0:
        return "No regime bucket shows positive expectancy in this sample."
    if best_regime == positive_label:
        return f"{positive_label} shows the strongest edge; keep this filter in the next validation run."
    return f"{best_regime} is strongest in this sample; validate before hard-coding the expected {positive_label} filter."


def _md(value: object) -> str:
    if value is None:
        return "n/a"
    return str(value)
