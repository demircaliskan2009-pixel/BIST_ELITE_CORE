"""Execution Engine typed models.

PRD reference: §7 Execution Engine.
"""

from __future__ import annotations

from dataclasses import dataclass

from crypto_core.risk.models import RiskEvaluation


class ExecutionMode(str):
    """Execution mode — controls whether real orders are placed."""

    pass


ExecutionMode.DRY_RUN = ExecutionMode("dry_run")  # No file writes, no state mutations
ExecutionMode.PAPER = ExecutionMode("paper")  # Logs paper fills, no exchange calls
# ExecutionMode.LIVE is NOT implemented yet — reserved for future adapter injection


class OrderIntent(str):
    """Requested trade direction."""

    pass


OrderIntent.BUY = OrderIntent("buy")
OrderIntent.SELL = OrderIntent("sell")


class RejectionReason(str):
    """Why an execution request was rejected."""

    pass


RejectionReason.INVALID_SYMBOL = RejectionReason("invalid_symbol")
RejectionReason.INCOMPLETE_PAYLOAD = RejectionReason("incomplete_payload")
RejectionReason.SYSTEM_STATE_DEFENSIVE = RejectionReason("system_state_defensive")
RejectionReason.RISK_NOT_APPROVED = RejectionReason("risk_not_approved")
RejectionReason.LIVE_NOT_ENABLED = RejectionReason("live_not_enabled")
RejectionReason.ZERO_SIZE = RejectionReason("zero_size")
RejectionReason.EXCEPTION_FAIL_CLOSED = RejectionReason("exception_fail_closed")


@dataclass(frozen=True)
class ExecutionRequest:
    """Input to the execution engine — built from a risk-approved payload.

    All fields are required. The engine rejects requests with missing data.
    """

    symbol: str
    exchange: str
    intent: OrderIntent
    size: float  # base currency quantity (positive)
    price_hint: float  # last known mid-price (for dry-run logging)
    risk_evaluation: RiskEvaluation
    timestamp_ns: int


@dataclass(frozen=True)
class ExecutionDecision:
    """Immutable result of one execution engine evaluation.

    order_id: generated UUID for dry-run / paper orders; None if rejected.
    mode: the mode under which this decision was made.
    """

    allowed: bool
    rejection_reason: RejectionReason | None  # None iff allowed=True
    mode: ExecutionMode
    order_id: str | None  # dry-run / paper generates a UUID; None if rejected
    evidence: dict[str, object]
    timestamp_ns: int

    @property
    def rejected(self) -> bool:
        return not self.allowed
