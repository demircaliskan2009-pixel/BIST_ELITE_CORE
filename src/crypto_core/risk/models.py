"""Risk Engine typed models — v1 + v2.

PRD reference: §1.14–§1.28 Risk and Execution.
"""

from __future__ import annotations

from dataclasses import dataclass

from crypto_core.edge.models import EdgeSignal
from crypto_core.guard.models import NoTradeDecision
from crypto_core.risk.contracts import PortfolioRiskSnapshot
from crypto_core.state.models import SystemState


class RiskDecision(str):
    """Outcome of a risk evaluation."""

    pass


RiskDecision.APPROVED = RiskDecision("approved")
RiskDecision.BLOCKED = RiskDecision("blocked")


class RiskBlockReason(str):
    """Reason a risk evaluation blocked a signal."""

    pass


# ── v1 block reasons (unchanged) ──────────────────────────────────────────
RiskBlockReason.SYSTEM_STATE_DEFENSIVE = RiskBlockReason("system_state_defensive")
RiskBlockReason.NO_TRADE_BLOCKED = RiskBlockReason("no_trade_blocked")
RiskBlockReason.TELEMETRY_INVALID = RiskBlockReason("telemetry_invalid")
RiskBlockReason.EDGE_EVIDENCE_INCOMPLETE = RiskBlockReason("edge_evidence_incomplete")
RiskBlockReason.EDGE_NOT_VALID = RiskBlockReason("edge_not_valid")
RiskBlockReason.EXCEPTION_FAIL_CLOSED = RiskBlockReason("exception_fail_closed")

# ── v2 block reasons (implemented in evaluate_v2) ──────────────────────────
#: Kill-switch level >= KS_BLOCK_THRESHOLD (2) — no new entries
RiskBlockReason.KS_BLOCKED = RiskBlockReason("ks_blocked")
#: DTL < minimum safe distance — position too close to liquidation
RiskBlockReason.DTL_UNSAFE = RiskBlockReason("dtl_unsafe")
#: Kelly f* <= 0 — no positive mathematical edge
RiskBlockReason.KELLY_NO_EDGE = RiskBlockReason("kelly_no_edge")
#: Kelly inputs invalid (win_rate or payoff_ratio out of range)
RiskBlockReason.KELLY_LIMIT = RiskBlockReason("kelly_limit")
#: CVaR99 exceeds hard limit
RiskBlockReason.CVAR_LIMIT = RiskBlockReason("cvar_limit")
#: Portfolio-level limit breached (exposure, positions, or leverage)
RiskBlockReason.PORTFOLIO_LIMIT = RiskBlockReason("portfolio_limit")

# ── legacy alias stubs kept for backward compat ───────────────────────────
RiskBlockReason.MARGIN_LIMIT = RiskBlockReason("margin_limit")
RiskBlockReason.KILL_SWITCH = RiskBlockReason("kill_switch")  # legacy alias for KS_BLOCKED


@dataclass(frozen=True)
class RiskEvaluation:
    """Immutable output of one risk engine evaluation cycle.

    v1 fields (positions 1–7) are unchanged — all existing code that
    constructs RiskEvaluation with keyword arguments continues to work.

    v2 optional fields (positions 8–11) default to safe values so v1
    construction paths produce valid objects.
    """

    # ── v1 fields (required, no defaults) ─────────────────────────────────
    decision: RiskDecision
    block_reason: RiskBlockReason | None  # None iff decision=APPROVED
    system_state: SystemState
    edge_signal: EdgeSignal
    no_trade_decision: NoTradeDecision
    evidence: dict[str, object]
    timestamp_ns: int

    # ── v2 optional fields (defaults maintain v1 compat) ──────────────────
    #: Active kill-switch level at evaluation time (0 = none)
    kill_switch_level: int = 0
    #: Computed Kelly fraction [0, max_fraction]; None if Kelly gate skipped
    kelly_fraction: float | None = None
    #: Distance-to-Liquidation % at evaluation time; None if DTL gate skipped
    dtl_pct: float | None = None
    #: Portfolio snapshot used for portfolio-level gates; None if gate skipped
    portfolio_snapshot: PortfolioRiskSnapshot | None = None

    @property
    def approved(self) -> bool:
        return self.decision == RiskDecision.APPROVED
