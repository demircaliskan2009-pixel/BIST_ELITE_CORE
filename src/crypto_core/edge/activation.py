"""Edge Activation Matrix — per-family pre-signal gate (PRD §1.5).

The activation matrix is evaluated AFTER the engine-level guard/state gates
and BEFORE each family evaluator is called.  It determines whether a specific
edge family is permitted to emit a tradable signal on this evaluation cycle.

Rules applied in priority order:
  1. Family not implemented (E/F/G) → BLOCKED: family_not_implemented
    2. System state restricted          → BLOCKED: system_state_restricted
    3. Data feed disconnected           → BLOCKED: data_disconnected
    4. Data feed in recovery            → BLOCKED: data_recovering
    5. Family liquidity below threshold → BLOCKED: liquidity_below_family_threshold
    6. Family edge health blocked       → BLOCKED: edge_health_low / edge_disabled
    7. Family transition restriction    → BLOCKED: regime_transition_blocked
    8. Funding family: no mark-price    → BLOCKED: funding_feed_unavailable

Activation decisions are deterministic and auditable: same inputs → same
output, with explicit reason codes, missing inputs, and evidence dicts.

PRD reference: §1.5 Activation Matrix.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from crypto_core.edge.models import EdgeFamily

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Families with at least a v1 implementation capable of running in paper mode.
_IMPLEMENTED_FAMILIES: frozenset[str] = frozenset(
    [
        EdgeFamily.ORDER_FLOW_IMBALANCE,
        EdgeFamily.FUNDING_RATE,
        EdgeFamily.VOLATILITY_TRANSITION,
        EdgeFamily.LIQUIDATION_SIGNAL,
    ]
)

#: Feed states that are considered "connected enough" for evaluation.
_CONNECTED_FEED_STATES: frozenset[str] = frozenset(["connected", "ready"])

_RESTRICTED_SYSTEM_STATES: frozenset[str] = frozenset(["DEFENSIVE", "CRISIS", "HALT"])

_HEALTHY_LIQUIDITY_MIN: float = 0.50
_MIN_RUNTIME_LIQUIDITY: float = 0.15
_EDGE_HEALTH_MIN: float = 0.30

_FAMILIES_REQUIRING_HEALTHY_LIQUIDITY: frozenset[str] = frozenset(
    [
        EdgeFamily.ORDER_FLOW_IMBALANCE,
        EdgeFamily.VOLATILITY_TRANSITION,
    ]
)

_FAMILIES_REQUIRING_MIN_LIQUIDITY: frozenset[str] = frozenset(
    [
        EdgeFamily.FUNDING_RATE,
        EdgeFamily.LIQUIDATION_SIGNAL,
    ]
)

_FAMILIES_BLOCKED_DURING_TRANSITION: frozenset[str] = frozenset(
    [
        EdgeFamily.ORDER_FLOW_IMBALANCE,
        EdgeFamily.FUNDING_RATE,
    ]
)


# ---------------------------------------------------------------------------
# Typed models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ActivationDecision:
    """Immutable result of one activation matrix evaluation.

    allowed=True  → family may be evaluated this cycle.
    allowed=False → family is blocked; reason explains why.
    evidence      → auditable context that produced this decision.
    """

    family: EdgeFamily
    allowed: bool
    reason: str  # deterministic reason code
    evidence: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ActivationContext:
    """All inputs the activation matrix may inspect for one evaluation cycle.

    Fields with None mean the upstream component is not yet wired.
    Absent optional inputs default to their safe/conservative value:
      mark_price_available=False → funding family blocked (fail-closed).
    """

    system_state: str  # str form of SystemState (e.g. "NORMAL")
    feed_connection_state: str  # "connected" | "ready" | "disconnected" | ...
    feed_recovery_state: str  # "ready" | "recovering"
    mark_price_available: bool  # True iff a MarkPriceEvent is present this cycle
    liquidity_score: float | None = None  # Regime tracker liquidity score [0, 1]
    regime_transition_active: bool | None = None  # None = no history yet
    edge_health_score: float | None = None  # None = no family history yet
    edge_fsm_state: str | None = None  # None = no family health snapshot yet


# ---------------------------------------------------------------------------
# Activation Matrix
# ---------------------------------------------------------------------------


class ActivationMatrix:
    """Deterministic per-family activation gate.

    Stateless: all inputs arrive via ActivationContext.
    Fail-closed on ambiguity: absent or unknown inputs default to BLOCKED.

    Usage::

        matrix = ActivationMatrix()
        for family in runtime_families:
            decision = matrix.evaluate(family, ctx)
            if not decision.allowed:
                # emit invalid signal with decision.reason
    """

    def evaluate(
        self,
        family: EdgeFamily,
        ctx: ActivationContext,
    ) -> ActivationDecision:
        """Return the activation decision for *family* given *ctx*.

        Always returns a deterministic ActivationDecision.  Never raises.
        """
        base_evidence: dict[str, object] = {
            "family": str(family),
            "system_state": ctx.system_state,
            "feed_connection_state": ctx.feed_connection_state,
            "feed_recovery_state": ctx.feed_recovery_state,
            "mark_price_available": ctx.mark_price_available,
            "liquidity_score": ctx.liquidity_score,
            "regime_transition_active": ctx.regime_transition_active,
            "edge_health_score": ctx.edge_health_score,
            "edge_fsm_state": ctx.edge_fsm_state,
        }
        missing_inputs: list[str] = []

        if ctx.liquidity_score is None:
            missing_inputs.append("liquidity_score")
        if ctx.regime_transition_active is None:
            missing_inputs.append("regime_transition_active")
        if ctx.edge_health_score is None:
            missing_inputs.append("edge_health_score")
        if ctx.edge_fsm_state is None:
            missing_inputs.append("edge_fsm_state")

        # Rule 1: family not implemented → always blocked
        if family not in _IMPLEMENTED_FAMILIES:
            return ActivationDecision(
                family=family,
                allowed=False,
                reason="family_not_implemented",
                evidence={
                    **base_evidence,
                    "supported_families": sorted(_IMPLEMENTED_FAMILIES),
                    "missing_inputs": missing_inputs,
                },
            )

        # Rule 2: system state restricted → block all families
        if ctx.system_state in _RESTRICTED_SYSTEM_STATES:
            return ActivationDecision(
                family=family,
                allowed=False,
                reason=f"system_state_restricted:{ctx.system_state}",
                evidence={
                    **base_evidence,
                    "restricted_states": sorted(_RESTRICTED_SYSTEM_STATES),
                    "missing_inputs": missing_inputs,
                },
            )

        # Rule 3: data feed disconnected → block all families
        if ctx.feed_connection_state not in _CONNECTED_FEED_STATES:
            return ActivationDecision(
                family=family,
                allowed=False,
                reason=f"data_disconnected:{ctx.feed_connection_state}",
                evidence={
                    **base_evidence,
                    "required_states": sorted(_CONNECTED_FEED_STATES),
                    "missing_inputs": missing_inputs,
                },
            )

        # Rule 4: data feed in recovery → block all families
        if ctx.feed_recovery_state == "recovering":
            return ActivationDecision(
                family=family,
                allowed=False,
                reason="data_recovering",
                evidence={**base_evidence, "missing_inputs": missing_inputs},
            )

        # Rule 5: family liquidity requirement (when liquidity evidence exists)
        if ctx.liquidity_score is not None:
            required_liquidity = None
            if family in _FAMILIES_REQUIRING_HEALTHY_LIQUIDITY:
                required_liquidity = _HEALTHY_LIQUIDITY_MIN
            elif family in _FAMILIES_REQUIRING_MIN_LIQUIDITY:
                required_liquidity = _MIN_RUNTIME_LIQUIDITY

            if required_liquidity is not None and ctx.liquidity_score < required_liquidity:
                return ActivationDecision(
                    family=family,
                    allowed=False,
                    reason="liquidity_below_family_threshold",
                    evidence={
                        **base_evidence,
                        "required_liquidity_score": required_liquidity,
                        "missing_inputs": missing_inputs,
                    },
                )

        # Rule 6: family edge health restriction
        if ctx.edge_fsm_state is not None and ctx.edge_fsm_state.upper() == "DISABLED":
            return ActivationDecision(
                family=family,
                allowed=False,
                reason="edge_disabled",
                evidence={**base_evidence, "missing_inputs": missing_inputs},
            )
        if ctx.edge_health_score is not None and ctx.edge_health_score < _EDGE_HEALTH_MIN:
            return ActivationDecision(
                family=family,
                allowed=False,
                reason="edge_health_low",
                evidence={
                    **base_evidence,
                    "minimum_edge_health_score": _EDGE_HEALTH_MIN,
                    "missing_inputs": missing_inputs,
                },
            )

        # Rule 7: transition restriction is family-specific
        if ctx.regime_transition_active is True and family in _FAMILIES_BLOCKED_DURING_TRANSITION:
            return ActivationDecision(
                family=family,
                allowed=False,
                reason="regime_transition_blocked",
                evidence={**base_evidence, "missing_inputs": missing_inputs},
            )

        # Rule 8: funding family requires mark-price feed
        if family == EdgeFamily.FUNDING_RATE and not ctx.mark_price_available:
            return ActivationDecision(
                family=family,
                allowed=False,
                reason="funding_feed_unavailable",
                evidence={
                    **base_evidence,
                    "required": "mark_price_event",
                    "hint": "wire MarkPriceEvent into MarketDataInput to enable",
                    "missing_inputs": missing_inputs,
                },
            )

        # All rules passed → allowed
        return ActivationDecision(
            family=family,
            allowed=True,
            reason="allowed_partial_context" if missing_inputs else "allowed",
            evidence={**base_evidence, "missing_inputs": missing_inputs},
        )
