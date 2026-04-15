"""Risk Engine typed models.

PRD reference: §1.14–§1.28 Risk and Execution.
"""

from __future__ import annotations

from dataclasses import dataclass

from crypto_core.edge.models import EdgeSignal
from crypto_core.guard.models import NoTradeDecision
from crypto_core.state.models import SystemState


class RiskDecision(str):
    """Outcome of a risk evaluation."""

    pass


RiskDecision.APPROVED = RiskDecision("approved")
RiskDecision.BLOCKED = RiskDecision("blocked")


class RiskBlockReason(str):
    """Reason a risk evaluation blocked a signal."""

    pass


RiskBlockReason.SYSTEM_STATE_DEFENSIVE = RiskBlockReason("system_state_defensive")
RiskBlockReason.NO_TRADE_BLOCKED = RiskBlockReason("no_trade_blocked")
RiskBlockReason.TELEMETRY_INVALID = RiskBlockReason("telemetry_invalid")
RiskBlockReason.EDGE_EVIDENCE_INCOMPLETE = RiskBlockReason("edge_evidence_incomplete")
RiskBlockReason.EDGE_NOT_VALID = RiskBlockReason("edge_not_valid")
RiskBlockReason.EXCEPTION_FAIL_CLOSED = RiskBlockReason("exception_fail_closed")

# Extension points (not yet implemented — require Kelly, CVaR, margin engines)
RiskBlockReason.KELLY_LIMIT = RiskBlockReason("kelly_limit")
RiskBlockReason.CVAR_LIMIT = RiskBlockReason("cvar_limit")
RiskBlockReason.MARGIN_LIMIT = RiskBlockReason("margin_limit")
RiskBlockReason.KILL_SWITCH = RiskBlockReason("kill_switch")


@dataclass(frozen=True)
class RiskEvaluation:
    """Immutable output of one risk engine evaluation cycle."""

    decision: RiskDecision
    block_reason: RiskBlockReason | None  # None iff decision=APPROVED
    system_state: SystemState
    edge_signal: EdgeSignal
    no_trade_decision: NoTradeDecision
    evidence: dict[str, object]
    timestamp_ns: int

    @property
    def approved(self) -> bool:
        return self.decision == RiskDecision.APPROVED
