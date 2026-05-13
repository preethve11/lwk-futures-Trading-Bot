"""Small smart-order-routing policy for paper/testnet execution."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OrderRoutingDecision:
    """Order type and reason selected by the routing policy."""

    order_type: str
    post_only: bool
    max_slippage_bps: float
    reason: str


class SmartOrderRouter:
    """Choose market vs limit execution from urgency and spread proxy."""

    def __init__(self, *, max_passive_spread_bps: float = 8.0, default_max_slippage_bps: float = 10.0) -> None:
        self.max_passive_spread_bps = max_passive_spread_bps
        self.default_max_slippage_bps = default_max_slippage_bps

    def route(self, *, urgency: float, spread_proxy_bps: float, edge_bps: float) -> OrderRoutingDecision:
        """Return a conservative order-routing decision."""
        normalized_urgency = min(max(urgency, 0.0), 1.0)
        if edge_bps <= 0:
            return OrderRoutingDecision(
                order_type="NONE",
                post_only=False,
                max_slippage_bps=0.0,
                reason="No positive expected edge after costs",
            )
        if normalized_urgency < 0.65 and spread_proxy_bps <= self.max_passive_spread_bps:
            return OrderRoutingDecision(
                order_type="LIMIT",
                post_only=True,
                max_slippage_bps=min(self.default_max_slippage_bps, edge_bps * 0.25),
                reason="Passive limit order preferred because urgency and spread are acceptable",
            )
        return OrderRoutingDecision(
            order_type="MARKET",
            post_only=False,
            max_slippage_bps=min(self.default_max_slippage_bps, edge_bps * 0.5),
            reason="Market order allowed because urgency or spread requires immediate execution",
        )
