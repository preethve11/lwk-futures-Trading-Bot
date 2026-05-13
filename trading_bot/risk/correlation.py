"""Portfolio-level correlated exposure checks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from trading_bot.core.types import SignalSide


@dataclass(frozen=True)
class Exposure:
    """Open exposure as a percentage of account equity."""

    symbol: str
    side: SignalSide
    equity_pct: float


def correlated_exposure_pct(
    exposures: list[Exposure],
    *,
    candidate_symbol: str,
    candidate_side: SignalSide,
    correlations: Mapping[tuple[str, str], float],
    min_abs_correlation: float = 0.75,
) -> float:
    """Return existing exposure correlated with the candidate trade."""
    normalized_candidate = candidate_symbol.strip().upper()
    total = 0.0
    for exposure in exposures:
        if exposure.side != candidate_side:
            continue
        correlation = _lookup_correlation(correlations, exposure.symbol, normalized_candidate)
        if abs(correlation) >= min_abs_correlation:
            total += exposure.equity_pct
    return total


def would_exceed_correlated_exposure(
    exposures: list[Exposure],
    *,
    candidate_symbol: str,
    candidate_side: SignalSide,
    candidate_equity_pct: float,
    correlations: Mapping[tuple[str, str], float],
    max_correlated_equity_pct: float,
    min_abs_correlation: float = 0.75,
) -> bool:
    """Return True when adding a trade would exceed correlated risk-on exposure."""
    existing = correlated_exposure_pct(
        exposures,
        candidate_symbol=candidate_symbol,
        candidate_side=candidate_side,
        correlations=correlations,
        min_abs_correlation=min_abs_correlation,
    )
    return existing + candidate_equity_pct > max_correlated_equity_pct


def _lookup_correlation(correlations: Mapping[tuple[str, str], float], left: str, right: str) -> float:
    normalized_left = left.strip().upper()
    normalized_right = right.strip().upper()
    if normalized_left == normalized_right:
        return 1.0
    return correlations.get((normalized_left, normalized_right), correlations.get((normalized_right, normalized_left), 0.0))
