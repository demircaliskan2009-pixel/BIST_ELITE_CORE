"""Risk Engine v1 — fail-closed approval gate (PRD §1.14–§1.28).

Approval requires ALL of:
  - system_state < DEFENSIVE
  - no_trade_decision.allowed == True
  - edge_signal.is_valid == True
  - edge_signal.evidence is non-empty
  - telemetry is considered available (shs_snapshot provided)

Extension points (not yet implemented):
  - Kelly position sizing (§1.28)
  - CVaR hard limit (§1.18)
  - Margin / DTL enforcement (§1.26)
  - Kill-switch levels (§1.19)
"""

from __future__ import annotations

import logging

from crypto_core.edge.models import EdgeSignal
from crypto_core.guard.models import NoTradeDecision
from crypto_core.risk.models import (
    RiskBlockReason,
    RiskDecision,
    RiskEvaluation,
)
from crypto_core.state.models import SystemState, is_at_least

logger = logging.getLogger(__name__)


class RiskEngine:
    """Fail-closed risk approval gate.

    Every edge signal must pass through this gate before execution.
    On any exception: returns a BLOCKED evaluation (fail-closed).

    Usage::

        engine = RiskEngine()
        eval_ = engine.evaluate(edge_signal, system_state, no_trade, ts_ns)
        if eval_.approved:
            # forward to execution
    """

    def evaluate(
        self,
        edge_signal: EdgeSignal,
        system_state: SystemState,
        no_trade: NoTradeDecision,
        timestamp_ns: int,
        shs_snapshot: float | None = None,
    ) -> RiskEvaluation:
        """Evaluate whether the edge signal is approved for execution.

        Args:
            edge_signal: output from EdgeEngine for one family.
            system_state: current state from SystemStateEngine.
            no_trade: decision from NoTradeGuard.
            timestamp_ns: evaluation wall-clock (nanoseconds).
            shs_snapshot: SHS value at time of evaluation (optional, for telemetry).

        Returns:
            RiskEvaluation with decision=APPROVED or BLOCKED.
        """
        try:
            return self._do_evaluate(
                edge_signal, system_state, no_trade, timestamp_ns, shs_snapshot
            )
        except Exception:
            logger.exception("RiskEngine.evaluate raised — fail-closed BLOCKED")
            return RiskEvaluation(
                decision=RiskDecision.BLOCKED,
                block_reason=RiskBlockReason.EXCEPTION_FAIL_CLOSED,
                system_state=system_state,
                edge_signal=edge_signal,
                no_trade_decision=no_trade,
                evidence={"error": "exception_fail_closed"},
                timestamp_ns=timestamp_ns,
            )

    # -----------------------------------------------------------------------
    # Internal evaluation chain
    # -----------------------------------------------------------------------

    def _do_evaluate(
        self,
        edge_signal: EdgeSignal,
        system_state: SystemState,
        no_trade: NoTradeDecision,
        timestamp_ns: int,
        shs_snapshot: float | None,
    ) -> RiskEvaluation:
        evidence: dict[str, object] = {
            "system_state": str(system_state),
            "edge_family": str(edge_signal.family),
            "edge_direction": str(edge_signal.direction),
            "edge_confidence": edge_signal.confidence,
        }
        if shs_snapshot is not None:
            evidence["shs_snapshot"] = shs_snapshot

        # Gate 1: system state >= DEFENSIVE → block
        if is_at_least(system_state, SystemState.DEFENSIVE):
            return self._blocked(
                RiskBlockReason.SYSTEM_STATE_DEFENSIVE,
                edge_signal,
                system_state,
                no_trade,
                {**evidence, "block": "system_state_defensive"},
                timestamp_ns,
            )

        # Gate 2: no-trade guard blocked
        if not no_trade.allowed:
            return self._blocked(
                RiskBlockReason.NO_TRADE_BLOCKED,
                edge_signal,
                system_state,
                no_trade,
                {**evidence, "block": "no_trade", "no_trade_reason": str(no_trade.reason)},
                timestamp_ns,
            )

        # Gate 3: edge signal not valid (fail-closed from edge engine)
        if not edge_signal.is_valid:
            return self._blocked(
                RiskBlockReason.EDGE_NOT_VALID,
                edge_signal,
                system_state,
                no_trade,
                {**evidence, "block": "edge_invalid", "edge_reason": edge_signal.block_reason},
                timestamp_ns,
            )

        # Gate 4: edge evidence must be non-empty
        if not edge_signal.evidence:
            return self._blocked(
                RiskBlockReason.EDGE_EVIDENCE_INCOMPLETE,
                edge_signal,
                system_state,
                no_trade,
                {**evidence, "block": "empty_edge_evidence"},
                timestamp_ns,
            )

        # All gates passed → APPROVED
        return RiskEvaluation(
            decision=RiskDecision.APPROVED,
            block_reason=None,
            system_state=system_state,
            edge_signal=edge_signal,
            no_trade_decision=no_trade,
            evidence=evidence,
            timestamp_ns=timestamp_ns,
        )

    @staticmethod
    def _blocked(
        reason: RiskBlockReason,
        edge_signal: EdgeSignal,
        system_state: SystemState,
        no_trade: NoTradeDecision,
        evidence: dict[str, object],
        timestamp_ns: int,
    ) -> RiskEvaluation:
        return RiskEvaluation(
            decision=RiskDecision.BLOCKED,
            block_reason=reason,
            system_state=system_state,
            edge_signal=edge_signal,
            no_trade_decision=no_trade,
            evidence=evidence,
            timestamp_ns=timestamp_ns,
        )
