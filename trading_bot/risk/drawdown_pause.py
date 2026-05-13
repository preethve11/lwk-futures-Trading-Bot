"""Drawdown-triggered pause logic for paper/testnet promotion."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass(frozen=True)
class DrawdownPauseDecision:
    """Decision returned by the drawdown pause circuit."""

    paused: bool
    drawdown_pct: float
    resume_after: datetime | None = None
    reason: str = ""


def evaluate_drawdown_pause(
    equity_curve: list[float],
    *,
    threshold_pct: float = 8.0,
    pause_hours: int = 48,
    as_of: datetime | None = None,
) -> DrawdownPauseDecision:
    """Return a pause decision when equity drawdown breaches the configured threshold."""
    if not equity_curve:
        return DrawdownPauseDecision(paused=False, drawdown_pct=0.0)
    peak = max(equity_curve)
    current = equity_curve[-1]
    if peak <= 0:
        return DrawdownPauseDecision(paused=False, drawdown_pct=0.0)
    drawdown_pct = ((peak - current) / peak) * 100.0
    if drawdown_pct < threshold_pct:
        return DrawdownPauseDecision(paused=False, drawdown_pct=drawdown_pct)
    now = as_of or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return DrawdownPauseDecision(
        paused=True,
        drawdown_pct=drawdown_pct,
        resume_after=now + timedelta(hours=pause_hours),
        reason=f"Equity drawdown {drawdown_pct:.2f}% breached {threshold_pct:.2f}% pause threshold.",
    )
