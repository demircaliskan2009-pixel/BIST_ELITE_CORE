"""Risk Engine v1 + v2 â€” fail-closed approval gate (PRD Â§1.14â€“Â§1.28).

v1 evaluate() â€” 4-gate chain (unchanged, fully backward compatible).
v2 evaluate_v2() â€” extends v1 with 5 additional gates:
  Gate 5: kill-switch level enforcement (Â§1.19)
  Gate 6: DTL / distance-to-liquidation enforcement (Â§1.26)
  Gate 7: Kelly criterion sizing contract (Â§1.28)
  Gate 8: CVaR limit check (Â§1.18)
  Gate 9: portfolio-level exposure / leverage limits

All gates fail-closed: any unhandled exception â†’ BLOCKED.
Same inputs always produce the same decision (deterministic).
"""

from __future__ import annotations

import logging

from crypto_core.edge.models import EdgeSignal
from crypto_core.guard.models import NoTradeDecision
from crypto_core.risk.contracts import (
    KS_BLOCK_THRESHOLD,
    RiskInput,
)
from crypto_core.risk.models import (
    RiskBlockReason,
    RiskDecision,
    RiskEvaluation,
)
from crypto_core.state.models import SystemState, is_at_least

logger = logging.getLogger(__name__)

#: System-wide maximum leverage (PRD invariant: 3Ã—)
_MAX_LEVERAGE: float = 3.0


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
            return self._do_evaluate(edge_signal, system_state, no_trade, timestamp_ns, shs_snapshot)
        except Exception:
            logger.exception("RiskEngine.evaluate raised â€” fail-closed BLOCKED")
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

        # Gate 1: system state >= DEFENSIVE â†’ block
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

        # All gates passed â†’ APPROVED
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

    # =======================================================================
    # v2 evaluation chain
    # =======================================================================

    def evaluate_v2(self, risk_input: RiskInput) -> RiskEvaluation:
        """Full v2 evaluation â€” extends v1 with KS, DTL, Kelly, CVaR, portfolio gates.

        Args:
            risk_input: complete v2 input contract (see RiskInput).

        Returns:
            RiskEvaluation with all v2 fields populated.  Never raises.
        """
        try:
            return self._do_evaluate_v2(risk_input)
        except Exception:
            logger.exception("RiskEngine.evaluate_v2 raised â€” fail-closed BLOCKED")
            return RiskEvaluation(
                decision=RiskDecision.BLOCKED,
                block_reason=RiskBlockReason.EXCEPTION_FAIL_CLOSED,
                system_state=risk_input.system_state,
                edge_signal=risk_input.edge_signal,
                no_trade_decision=risk_input.no_trade,
                evidence={"error": "exception_fail_closed"},
                timestamp_ns=risk_input.timestamp_ns,
                kill_switch_level=risk_input.kill_switch_level,
            )

    def _do_evaluate_v2(self, r: RiskInput) -> RiskEvaluation:  # noqa: C901
        evidence: dict[str, object] = {
            "system_state": str(r.system_state),
            "edge_family": str(r.edge_signal.family),
            "edge_direction": str(r.edge_signal.direction),
            "edge_confidence": r.edge_signal.confidence,
            "kill_switch_level": r.kill_switch_level,
        }
        if r.shs_snapshot is not None:
            evidence["shs_snapshot"] = r.shs_snapshot

        # â”€â”€ v1 gates (1â€“4) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        # Gate 1: system state >= DEFENSIVE
        if is_at_least(r.system_state, SystemState.DEFENSIVE):
            return self._blocked_v2(
                RiskBlockReason.SYSTEM_STATE_DEFENSIVE,
                r,
                {**evidence, "block": "system_state_defensive"},
            )

        # Gate 2: no-trade guard blocked
        if not r.no_trade.allowed:
            return self._blocked_v2(
                RiskBlockReason.NO_TRADE_BLOCKED,
                r,
                {
                    **evidence,
                    "block": "no_trade",
                    "no_trade_reason": str(r.no_trade.reason),
                },
            )

        # Gate 3: edge signal not valid
        if not r.edge_signal.is_valid:
            return self._blocked_v2(
                RiskBlockReason.EDGE_NOT_VALID,
                r,
                {
                    **evidence,
                    "block": "edge_invalid",
                    "edge_reason": r.edge_signal.block_reason,
                },
            )

        # Gate 4: edge evidence non-empty
        if not r.edge_signal.evidence:
            return self._blocked_v2(
                RiskBlockReason.EDGE_EVIDENCE_INCOMPLETE,
                r,
                {**evidence, "block": "empty_edge_evidence"},
            )

        # â”€â”€ v2 gates (5â€“9) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        # Gate 5: kill-switch level
        ks_block = self._gate_kill_switch(r, evidence)
        if ks_block is not None:
            return ks_block

        # Gate 6: DTL (skip if dtl is None)
        dtl_pct: float | None = None
        if r.dtl is not None:
            dtl_block, dtl_pct = self._gate_dtl(r, evidence)
            if dtl_block is not None:
                return dtl_block

        # Gate 7: Kelly (skip if kelly is None)
        kelly_fraction: float | None = None
        if r.kelly is not None:
            kelly_block, kelly_fraction = self._gate_kelly(r, evidence)
            if kelly_block is not None:
                return kelly_block

        # Gate 8: CVaR (skip if cvar is None)
        if r.cvar is not None:
            cvar_block = self._gate_cvar(r, evidence)
            if cvar_block is not None:
                return cvar_block

        # Gate 9: Portfolio (skip if portfolio is None)
        if r.portfolio is not None:
            portfolio_block = self._gate_portfolio(r, evidence)
            if portfolio_block is not None:
                return portfolio_block

        # All gates passed â†’ APPROVED
        return RiskEvaluation(
            decision=RiskDecision.APPROVED,
            block_reason=None,
            system_state=r.system_state,
            edge_signal=r.edge_signal,
            no_trade_decision=r.no_trade,
            evidence=evidence,
            timestamp_ns=r.timestamp_ns,
            kill_switch_level=r.kill_switch_level,
            kelly_fraction=kelly_fraction,
            dtl_pct=dtl_pct,
            portfolio_snapshot=r.portfolio,
        )

    # -----------------------------------------------------------------------
    # Gate implementations
    # -----------------------------------------------------------------------

    def _gate_kill_switch(
        self,
        r: RiskInput,
        evidence: dict[str, object],
    ) -> RiskEvaluation | None:
        """Gate 5: kill-switch level enforcement (PRD Â§1.19)."""
        if r.kill_switch_level < KS_BLOCK_THRESHOLD:
            return None
        evidence["block"] = f"ks_level_{r.kill_switch_level}"
        return self._blocked_v2(RiskBlockReason.KS_BLOCKED, r, evidence)

    def _gate_dtl(
        self,
        r: RiskInput,
        evidence: dict[str, object],
    ) -> tuple[RiskEvaluation | None, float | None]:
        """Gate 6: Distance-to-Liquidation enforcement (PRD Â§1.26).

        Returns (block_result, dtl_pct).  block_result is None on pass.
        """
        dtl = r.dtl
        assert dtl is not None  # guaranteed by caller

        # liq_price=0 â†’ data unavailable â†’ skip gate, note in evidence
        if dtl.liquidation_price <= 0.0:
            evidence["dtl_status"] = "liquidation_price_unavailable"
            return None, None

        if dtl.current_price <= 0.0:
            evidence["dtl_status"] = "invalid_current_price"
            evidence["block"] = "dtl_invalid_price"
            return self._blocked_v2(RiskBlockReason.DTL_UNSAFE, r, evidence), None

        dtl_pct = abs(dtl.current_price - dtl.liquidation_price) / dtl.current_price * 100.0
        evidence["dtl_pct"] = dtl_pct
        evidence["dtl_min_safe_pct"] = dtl.min_safe_distance_pct

        if dtl_pct < dtl.min_safe_distance_pct:
            evidence["block"] = f"dtl_unsafe:{dtl_pct:.2f}%<{dtl.min_safe_distance_pct:.2f}%"
            return self._blocked_v2(RiskBlockReason.DTL_UNSAFE, r, evidence), dtl_pct

        return None, dtl_pct

    def _gate_kelly(
        self,
        r: RiskInput,
        evidence: dict[str, object],
    ) -> tuple[RiskEvaluation | None, float | None]:
        """Gate 7: Kelly criterion sizing (PRD Â§1.28).

        Formula: f* = (p * b - q) / b
          p = win_rate, q = 1 - p, b = payoff_ratio

        Returns (block_result, kelly_fraction).  block_result is None on pass.
        """
        kelly = r.kelly
        assert kelly is not None  # guaranteed by caller

        # Validate inputs first â€” invalid inputs block (fail-closed)
        if not (0.0 < kelly.win_rate < 1.0):
            evidence["kelly_error"] = f"invalid_win_rate:{kelly.win_rate}"
            evidence["block"] = "kelly_invalid_win_rate"
            return self._blocked_v2(RiskBlockReason.KELLY_LIMIT, r, evidence), None

        if kelly.payoff_ratio <= 0.0:
            evidence["kelly_error"] = f"invalid_payoff_ratio:{kelly.payoff_ratio}"
            evidence["block"] = "kelly_invalid_payoff_ratio"
            return self._blocked_v2(RiskBlockReason.KELLY_LIMIT, r, evidence), None

        # Discrete Kelly formula (exact, no approximation)
        # f* = (p * b - q) / b  where q = 1 - p
        q = 1.0 - kelly.win_rate
        f_star = (kelly.win_rate * kelly.payoff_ratio - q) / kelly.payoff_ratio

        evidence["kelly_f_star"] = f_star
        evidence["kelly_win_rate"] = kelly.win_rate
        evidence["kelly_payoff_ratio"] = kelly.payoff_ratio

        if f_star <= 0.0:
            # Non-positive Kelly: edge has no positive expected value â†’ block
            evidence["block"] = f"kelly_no_edge:f*={f_star:.6f}"
            return self._blocked_v2(RiskBlockReason.KELLY_NO_EDGE, r, evidence), None

        capped = min(f_star, kelly.max_fraction)
        evidence["kelly_fraction"] = capped
        evidence["kelly_capped"] = capped < f_star

        return None, capped

    def _gate_cvar(
        self,
        r: RiskInput,
        evidence: dict[str, object],
    ) -> RiskEvaluation | None:
        """Gate 8: CVaR limit check (PRD Â§1.18).

        Returns block_result or None on pass / data unavailable.
        """
        cvar = r.cvar
        assert cvar is not None  # guaranteed by caller

        evidence["cvar_available"] = cvar.available
        evidence["cvar_history_count"] = cvar.history_count

        if cvar.cvar99_pct is None:
            evidence["cvar_status"] = "unavailable"
            return None

        evidence["cvar99_pct"] = cvar.cvar99_pct
        evidence["cvar_limit_pct"] = cvar.cvar_limit_pct
        if cvar.var99_pct is not None:
            evidence["var99_pct"] = cvar.var99_pct

        if cvar.cvar99_pct > cvar.cvar_limit_pct:
            evidence["block"] = f"cvar_exceeded:{cvar.cvar99_pct:.2f}>{cvar.cvar_limit_pct:.2f}"
            return self._blocked_v2(RiskBlockReason.CVAR_LIMIT, r, evidence)

        return None

    def _gate_portfolio(
        self,
        r: RiskInput,
        evidence: dict[str, object],
    ) -> RiskEvaluation | None:
        """Gate 9: Portfolio-level limits (PRD Â§1.26).

        Checks: system leverage cap, exposure cap, concurrent positions cap.
        Returns block_result or None on pass.
        """
        p = r.portfolio
        assert p is not None  # guaranteed by caller

        evidence["portfolio_exposure_usd"] = p.total_exposure_usd
        evidence["portfolio_positions"] = p.active_position_count
        evidence["portfolio_max_leverage"] = p.max_leverage_in_use

        # Hard cap: system-wide 3Ã— leverage invariant (PRD invariant)
        if p.max_leverage_in_use > _MAX_LEVERAGE:
            evidence["block"] = f"portfolio_leverage:{p.max_leverage_in_use:.2f}>{_MAX_LEVERAGE:.2f}"
            return self._blocked_v2(RiskBlockReason.PORTFOLIO_LIMIT, r, evidence)

        # Notional exposure cap
        if p.total_exposure_usd > p.max_total_exposure_usd:
            evidence["block"] = f"portfolio_exposure:{p.total_exposure_usd:.2f}>{p.max_total_exposure_usd:.2f}"
            return self._blocked_v2(RiskBlockReason.PORTFOLIO_LIMIT, r, evidence)

        # Concurrent position cap
        if p.active_position_count >= p.max_concurrent_positions:
            evidence["block"] = f"portfolio_positions:{p.active_position_count}>={p.max_concurrent_positions}"
            return self._blocked_v2(RiskBlockReason.PORTFOLIO_LIMIT, r, evidence)

        return None

    # -----------------------------------------------------------------------
    # v2 helper
    # -----------------------------------------------------------------------

    @staticmethod
    def _blocked_v2(
        reason: RiskBlockReason,
        r: RiskInput,
        evidence: dict[str, object],
    ) -> RiskEvaluation:
        return RiskEvaluation(
            decision=RiskDecision.BLOCKED,
            block_reason=reason,
            system_state=r.system_state,
            edge_signal=r.edge_signal,
            no_trade_decision=r.no_trade,
            evidence=evidence,
            timestamp_ns=r.timestamp_ns,
            kill_switch_level=r.kill_switch_level,
        )
