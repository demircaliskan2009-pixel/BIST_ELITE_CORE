"""Edge Engine typed models.

Contracts shared across all edge families.

PRD reference: §1.1–§1.13.
"""

from __future__ import annotations

from dataclasses import dataclass


class EdgeFamily(str):
    """Registered edge families (v1 subset + Phase 4B additions)."""

    pass


EdgeFamily.ORDER_FLOW_IMBALANCE = EdgeFamily("order_flow_imbalance")  # Family A
EdgeFamily.FUNDING_RATE = EdgeFamily("funding_rate")                  # Family B
EdgeFamily.VOLATILITY_TRANSITION = EdgeFamily("volatility_transition") # Family C
EdgeFamily.LIQUIDATION_SIGNAL = EdgeFamily("liquidation_signal")       # Family D


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
    confidence: float         # [0.0, 1.0] — signal strength
    score: float              # raw family-specific score (signed)
    evidence: dict[str, object]
    timestamp_ns: int
    is_valid: bool            # False = fail-closed block
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
