"""Crowding and exchange-stress filters for futures strategies."""

from __future__ import annotations

from dataclasses import dataclass, field

from trading_bot.core.types import SignalSide


@dataclass(frozen=True)
class CrowdingThresholds:
    """Configurable thresholds for crowding and exchange-stress blocks."""

    funding_rate_abs_long_max: float = 0.0003
    funding_rate_abs_short_max: float = 0.0003
    funding_rate_delta_max: float = 0.0001
    open_interest_spike_pct_max: float = 12.0
    adl_quantile_max: float = 3.0
    liquidation_spike_ratio_max: float = 3.0
    volatility_shock_percentile_min: float = 0.9


@dataclass(frozen=True)
class CrowdingSnapshot:
    """Point-in-time crowding inputs attached to a signal decision."""

    funding_rate: float = 0.0
    funding_rate_delta_8h: float = 0.0
    open_interest_change_pct: float = 0.0
    adl_quantile: float = 0.0
    liquidation_spike_ratio: float = 0.0
    volatility_percentile: float = 0.0


@dataclass(frozen=True)
class CrowdingDecision:
    """Crowding filter decision plus normalized rejection categories."""

    blocked: bool
    reasons: list[str] = field(default_factory=list)


def evaluate_crowding(
    snapshot: CrowdingSnapshot,
    thresholds: CrowdingThresholds,
    *,
    side: SignalSide | None = None,
) -> CrowdingDecision:
    """Return whether a signal should be blocked by crowding/stress inputs."""
    reasons: list[str] = []
    funding_delta_spike = snapshot.funding_rate_delta_8h > thresholds.funding_rate_delta_max
    open_interest_spike = snapshot.open_interest_change_pct > thresholds.open_interest_spike_pct_max
    volatility_shock = snapshot.volatility_percentile >= thresholds.volatility_shock_percentile_min

    if side == SignalSide.LONG and snapshot.funding_rate > thresholds.funding_rate_abs_long_max:
        reasons.append("funding_too_expensive")
    if side == SignalSide.SHORT and snapshot.funding_rate < -thresholds.funding_rate_abs_short_max:
        reasons.append("funding_too_expensive")
    if funding_delta_spike:
        reasons.append("funding_delta_spike")
    if open_interest_spike:
        reasons.append("open_interest_spike")
    if snapshot.adl_quantile >= thresholds.adl_quantile_max:
        reasons.append("adl_risk")
    if snapshot.liquidation_spike_ratio >= thresholds.liquidation_spike_ratio_max:
        reasons.append("liquidation_spike")
    if funding_delta_spike and open_interest_spike and volatility_shock:
        reasons.append("market_stress")

    return CrowdingDecision(blocked=bool(reasons), reasons=reasons)
