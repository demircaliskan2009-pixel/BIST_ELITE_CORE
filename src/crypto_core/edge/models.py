"""Edge Engine typed models.

Contracts shared across all edge families.

PRD reference: §1.1–§1.13.
"""

from __future__ import annotations

from dataclasses import dataclass


class EdgeFamily(str):
    """Registered edge families (v1 subset + Phase 4B additions)."""

    pass


EdgeFamily.ORDER_FLOW_IMBALANCE = EdgeFamily("order_flow_imbalance")  # Project tag for PRD Family A
EdgeFamily.FUNDING_RATE = EdgeFamily("funding_rate")  # Project tag for PRD Family B
EdgeFamily.VOLATILITY_TRANSITION = EdgeFamily("volatility_transition")  # Project tag retained; maps to PRD Family D
EdgeFamily.LIQUIDATION_SIGNAL = EdgeFamily("liquidation_signal")  # Project tag retained; maps to PRD Family C
# Phase 6B contracts — not yet implemented; runtime blocks them (fail-closed).
EdgeFamily.CROSS_EXCHANGE_SPREAD = EdgeFamily("cross_exchange_spread")  # Project tag for PRD Family E
EdgeFamily.LATENCY_ARBITRAGE = EdgeFamily("latency_arbitrage")  # Project tag for PRD Family F
EdgeFamily.VOL_SURFACE_SKEW = EdgeFamily("vol_surface_skew")  # Project tag for PRD Family G


_PRD_FAMILY_CODES: dict[EdgeFamily, str] = {
    EdgeFamily.ORDER_FLOW_IMBALANCE: "A",
    EdgeFamily.FUNDING_RATE: "B",
    EdgeFamily.LIQUIDATION_SIGNAL: "C",
    EdgeFamily.VOLATILITY_TRANSITION: "D",
    EdgeFamily.CROSS_EXCHANGE_SPREAD: "E",
    EdgeFamily.LATENCY_ARBITRAGE: "F",
    EdgeFamily.VOL_SURFACE_SKEW: "G",
}

_PRD_FAMILY_NAMES: dict[EdgeFamily, str] = {
    EdgeFamily.ORDER_FLOW_IMBALANCE: "order_flow",
    EdgeFamily.FUNDING_RATE: "funding",
    EdgeFamily.LIQUIDATION_SIGNAL: "liquidation",
    EdgeFamily.VOLATILITY_TRANSITION: "volatility",
    EdgeFamily.CROSS_EXCHANGE_SPREAD: "cross_exchange",
    EdgeFamily.LATENCY_ARBITRAGE: "session_handoff",
    EdgeFamily.VOL_SURFACE_SKEW: "btc_dominance",
}


def edge_prd_family_code(family: EdgeFamily) -> str:
    """Return the authoritative PRD family code for a project family tag."""
    return _PRD_FAMILY_CODES.get(family, "UNKNOWN")


def edge_prd_family_name(family: EdgeFamily) -> str:
    """Return the authoritative PRD family name for a project family tag."""
    return _PRD_FAMILY_NAMES.get(family, "unknown")


class SignalDirection(str):
    """Direction of an edge signal."""

    pass


SignalDirection.BUY = SignalDirection("buy")
SignalDirection.SELL = SignalDirection("sell")
SignalDirection.NEUTRAL = SignalDirection("neutral")


@dataclass(frozen=True)
class EdgeSignal:
    """Immutable output of one edge evaluation cycle.

    is_valid=False means the edge encountered a blocking condition
    (stale inputs, insufficient data, guard block, etc.).
    When is_valid=False, direction=NEUTRAL and confidence=0.0.

    PRD reference: §1.6 EHS lifecycle — only ACTIVE edges produce signals.
    """

    family: EdgeFamily
    symbol: str
    exchange: str
    direction: SignalDirection
    confidence: float  # [0.0, 1.0] — signal strength
    score: float  # raw family-specific score (signed)
    evidence: dict[str, object]
    timestamp_ns: int
    is_valid: bool  # False = fail-closed block
    block_reason: str | None  # human-readable if is_valid=False

    @classmethod
    def invalid(
        cls,
        family: EdgeFamily,
        symbol: str,
        exchange: str,
        reason: str,
        timestamp_ns: int,
        evidence: dict[str, object] | None = None,
    ) -> EdgeSignal:
        """Factory for a fail-closed invalid signal."""
        return cls(
            family=family,
            symbol=symbol,
            exchange=exchange,
            direction=SignalDirection.NEUTRAL,
            confidence=0.0,
            score=0.0,
            evidence=evidence or {"block_reason": reason},
            timestamp_ns=timestamp_ns,
            is_valid=False,
            block_reason=reason,
        )
