"""Route binding — metadata-gated routing into the execution path (Phase 9C).

Binds venue scoring, expected-cost routing, and venue metadata into a
single route decision that enters the execution flow.  Every routing
attempt produces a fully auditable RouteDecision explaining *why* a
venue was selected, abstained, or blocked.

Design invariants:
  - Fail-closed: missing or stale metadata → BLOCK or ABSTAIN, never silent route.
  - DEGRADED venue is never silently treated as healthy.
  - BLOCKED venue is never routed to.
  - If all venues fail metadata checks → ABSTAIN (NO TRADE).
  - Each venue produces a VenueEvaluation with explicit reason codes.
  - RouteDecision is frozen and serializable for audit replay.

PRD reference: §7 Execution Engine, Research Memory §5–§6 Venue Scoring.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum

from crypto_core.execution.venue_metadata import MetadataFreshness, VenueMetadataSnapshot, VenueOperationalStatus
from crypto_core.execution.venue_scoring import (
    ExpectedCostEstimate,
    RoutingAction,
    RoutingEngine,
    RoutingRecommendation,
    VenueBlockReason,
    VenueScore,
    VenueScoreComponents,
)

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class RouteDecisionOutcome(str, Enum):
    """Final routing outcome that enters the execution path."""

    ROUTE_TO_VENUE = "route_to_venue"
    ABSTAIN = "abstain"
    BLOCK = "block"
    FALLBACK_NOT_ALLOWED = "fallback_not_allowed"


class VenueRejectReason(str, Enum):
    """Why a specific venue was not selected."""

    METADATA_UNAVAILABLE = "metadata_unavailable"
    METADATA_STALE = "metadata_stale"
    FEE_DATA_MISSING = "fee_data_missing"
    VENUE_NOT_OPERATIONAL = "venue_not_operational"
    VENUE_DEGRADED = "venue_degraded"
    VENUE_BLOCKED = "venue_blocked"
    SCORE_TOO_LOW = "score_too_low"
    HIGHER_COST = "higher_cost"
    EXECUTION_NOT_PERMITTED = "execution_not_permitted"


# ---------------------------------------------------------------------------
# Per-venue evaluation record
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VenueEvaluation:
    """Auditable per-venue routing evaluation result.

    One of these is produced for each venue considered during routing.
    """

    venue: str
    symbol: str
    selected: bool
    reject_reasons: tuple[VenueRejectReason, ...] = ()
    metadata_snapshot: VenueMetadataSnapshot | None = None
    venue_score: VenueScore | None = None
    expected_cost: ExpectedCostEstimate | None = None
    execution_permitted: bool = False
    evidence: dict[str, object] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# RouteDecision — the frozen routing result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RouteDecision:
    """Immutable route decision for one execution attempt.

    Captures the full routing evaluation: which venues were considered,
    which won, which were rejected and why.
    """

    symbol: str
    outcome: RouteDecisionOutcome
    selected_venue: str | None = None
    selected_cost_bps: float | None = None
    venue_evaluations: tuple[VenueEvaluation, ...] = ()
    routing_recommendation: RoutingRecommendation | None = None
    reason: str = ""
    decided_at_ns: int = 0
    evidence: dict[str, object] = field(default_factory=dict)

    @property
    def is_routable(self) -> bool:
        return self.outcome == RouteDecisionOutcome.ROUTE_TO_VENUE

    @property
    def blocked_venues(self) -> tuple[str, ...]:
        return tuple(e.venue for e in self.venue_evaluations if not e.selected)


def route_decision_to_dict(d: RouteDecision) -> dict:
    """Serialize a RouteDecision to a plain dict for persistence/audit."""
    return {
        "symbol": d.symbol,
        "outcome": d.outcome.value,
        "selected_venue": d.selected_venue,
        "selected_cost_bps": d.selected_cost_bps,
        "reason": d.reason,
        "decided_at_ns": d.decided_at_ns,
        "venue_count": len(d.venue_evaluations),
        "blocked_venues": list(d.blocked_venues),
        "evidence": d.evidence,
    }


# ---------------------------------------------------------------------------
# MetadataGatedRouter
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MetadataGatedRouterConfig:
    """Configuration for the metadata-gated router.

    allow_estimated_fees: if True, ESTIMATED fee data is acceptable.
    allow_degraded_venues: if True, DEGRADED venues can still route
        (with penalty). If False, DEGRADED → reject (fail-closed).
    require_funding_data: if True, missing funding data blocks routing.
    """

    allow_estimated_fees: bool = True
    allow_degraded_venues: bool = False
    require_funding_data: bool = False


class MetadataGatedRouter:
    """Metadata-aware routing engine — gates venue access by metadata quality.

    Wraps RoutingEngine (venue scoring + expected cost) and adds metadata
    checks before producing a final RouteDecision.

    Flow:
      1. For each venue+symbol pair: check VenueMetadataSnapshot.
      2. Reject venues with missing/stale/blocked metadata.
      3. Feed remaining venues into RoutingEngine.recommend().
      4. If RoutingEngine returns ROUTE → ROUTE_TO_VENUE.
      5. If all venues rejected by metadata → BLOCK.
      6. If RoutingEngine abstains (all scored below threshold) → ABSTAIN.

    Usage::

        router = MetadataGatedRouter(
            routing_engine=routing_engine,
        )
        decision = router.decide(
            symbol="BTCUSDT",
            venue_metadata={"binance": snap_b, "bybit": snap_by},
            venue_components={"binance": components_b, "bybit": components_by},
            half_spread_by_venue={"binance": 2.5, "bybit": 3.0},
            expected_impact_bps=1.0,
            is_maker=False,
        )

    Invariants:
      - Never silently routes to a venue with missing metadata.
      - Every venue produces a VenueEvaluation with explicit reasons.
      - DEGRADED venues rejected unless config allows them.
      - BLOCKED venues always rejected.
    """

    def __init__(
        self,
        routing_engine: RoutingEngine,
        config: MetadataGatedRouterConfig | None = None,
    ) -> None:
        self._routing_engine = routing_engine
        self._config = config or MetadataGatedRouterConfig()

    def decide(
        self,
        *,
        symbol: str,
        venue_metadata: dict[str, VenueMetadataSnapshot],
        venue_components: dict[str, VenueScoreComponents],
        half_spread_by_venue: dict[str, float],
        expected_impact_bps: float,
        is_maker: bool,
        funding_rate_by_venue: dict[str, float] | None = None,
        venue_block_reasons: dict[str, VenueBlockReason] | None = None,
    ) -> RouteDecision:
        """Produce a metadata-gated routing decision.

        Args:
            symbol: the instrument to route.
            venue_metadata: metadata snapshot per venue.
            venue_components: scoring components per venue.
            half_spread_by_venue: current half-spread bps per venue.
            expected_impact_bps: expected market impact.
            is_maker: whether the order is expected to be a maker.
            funding_rate_by_venue: optional funding rate per venue.
            venue_block_reasons: optional explicit block reasons per venue.

        Returns:
            RouteDecision with full audit trail.
        """
        block_reasons = venue_block_reasons or {}
        evaluations: list[VenueEvaluation] = []
        eligible_venues: dict[str, tuple[VenueScoreComponents, VenueBlockReason]] = {}

        # Phase 1: metadata gating per venue
        for venue in sorted(venue_metadata.keys()):
            meta = venue_metadata[venue]
            rejects: list[VenueRejectReason] = []
            permitted = True

            # Gate 1: Fee data must exist and be usable
            if meta.fees is None:
                permitted = False
                rejects.append(VenueRejectReason.FEE_DATA_MISSING)
            elif not meta.fees.is_usable:
                permitted = False
                if meta.fees.freshness == MetadataFreshness.STALE:
                    rejects.append(VenueRejectReason.METADATA_STALE)
                else:
                    rejects.append(VenueRejectReason.FEE_DATA_MISSING)

            # Gate 2: Operational status
            if meta.operational is not None and not meta.operational.is_tradeable:
                is_degraded = meta.operational.status == VenueOperationalStatus.DEGRADED
                if is_degraded and self._config.allow_degraded_venues:
                    pass  # degraded allowed by config
                elif is_degraded:
                    permitted = False
                    rejects.append(VenueRejectReason.VENUE_DEGRADED)
                else:
                    permitted = False
                    rejects.append(VenueRejectReason.VENUE_NOT_OPERATIONAL)

            # Gate 3: Fee freshness (additional check beyond is_usable)
            if permitted and meta.fees is not None:
                if meta.fees.freshness == MetadataFreshness.STALE:
                    permitted = False
                    rejects.append(VenueRejectReason.METADATA_STALE)
                elif meta.fees.freshness == MetadataFreshness.UNAVAILABLE:
                    permitted = False
                    rejects.append(VenueRejectReason.FEE_DATA_MISSING)

            # Gate 4: Funding data requirement
            if permitted and self._config.require_funding_data:
                if not meta.has_funding_data:
                    permitted = False
                    rejects.append(VenueRejectReason.METADATA_UNAVAILABLE)

            # Gate 5: Explicit block
            if venue in block_reasons and block_reasons[venue] != VenueBlockReason.NONE:
                permitted = False
                rejects.append(VenueRejectReason.VENUE_BLOCKED)

            ev = {
                "metadata_permitted": meta.execution_permitted,
                "freshness": meta.freshness_summary,
            }

            if permitted and venue in venue_components:
                br = block_reasons.get(venue, VenueBlockReason.NONE)
                eligible_venues[venue] = (venue_components[venue], br)
                evaluations.append(
                    VenueEvaluation(
                        venue=venue,
                        symbol=symbol,
                        selected=False,  # updated later if selected
                        metadata_snapshot=meta,
                        execution_permitted=True,
                        evidence=ev,
                    )
                )
            else:
                if not rejects:
                    rejects.append(VenueRejectReason.METADATA_UNAVAILABLE)
                evaluations.append(
                    VenueEvaluation(
                        venue=venue,
                        symbol=symbol,
                        selected=False,
                        reject_reasons=tuple(rejects),
                        metadata_snapshot=meta,
                        execution_permitted=False,
                        evidence=ev,
                    )
                )

        # Phase 2: check if any venues survived metadata gating
        if not eligible_venues:
            all_reasons = set()
            for ev in evaluations:
                all_reasons.update(ev.reject_reasons)
            reason_str = ",".join(sorted(r.value for r in all_reasons)) if all_reasons else "no_venues"
            return RouteDecision(
                symbol=symbol,
                outcome=RouteDecisionOutcome.BLOCK,
                venue_evaluations=tuple(evaluations),
                reason=f"all_venues_rejected:{reason_str}",
                decided_at_ns=time.time_ns(),
                evidence={"eligible_count": 0, "total_count": len(venue_metadata)},
            )

        # Phase 3: run routing engine on eligible venues
        recommendation = self._routing_engine.recommend(
            symbol=symbol,
            venue_states=eligible_venues,
            half_spread_by_venue=half_spread_by_venue,
            expected_impact_bps=expected_impact_bps,
            is_maker=is_maker,
            funding_rate_by_venue=funding_rate_by_venue,
        )

        # Phase 4: build final decision from recommendation
        if recommendation.action == RoutingAction.ABSTAIN:
            # Update evaluations: venues that passed metadata but scored too low
            final_evals = []
            for ev in evaluations:
                if ev.execution_permitted and not ev.reject_reasons:
                    # Find its score from recommendation
                    score = next(
                        (s for s in recommendation.venue_scores if s.venue == ev.venue),
                        None,
                    )
                    final_evals.append(
                        VenueEvaluation(
                            venue=ev.venue,
                            symbol=ev.symbol,
                            selected=False,
                            reject_reasons=(VenueRejectReason.SCORE_TOO_LOW,),
                            metadata_snapshot=ev.metadata_snapshot,
                            venue_score=score,
                            execution_permitted=ev.execution_permitted,
                            evidence=ev.evidence,
                        )
                    )
                else:
                    final_evals.append(ev)

            return RouteDecision(
                symbol=symbol,
                outcome=RouteDecisionOutcome.ABSTAIN,
                routing_recommendation=recommendation,
                venue_evaluations=tuple(final_evals),
                reason=f"routing_abstain:{recommendation.reason}",
                decided_at_ns=time.time_ns(),
                evidence={
                    "eligible_count": len(eligible_venues),
                    "total_count": len(venue_metadata),
                },
            )

        # ROUTE — mark the winning venue
        selected = recommendation.recommended_venue
        final_evals = []
        for ev in evaluations:
            score = next(
                (s for s in recommendation.venue_scores if s.venue == ev.venue),
                None,
            )
            cost = next(
                (c for c in recommendation.venue_costs if c.venue == ev.venue),
                None,
            )
            is_selected = ev.venue == selected and ev.execution_permitted
            reject_reasons = ev.reject_reasons
            if not is_selected and ev.execution_permitted and not ev.reject_reasons:
                reject_reasons = (VenueRejectReason.HIGHER_COST,)
            final_evals.append(
                VenueEvaluation(
                    venue=ev.venue,
                    symbol=ev.symbol,
                    selected=is_selected,
                    reject_reasons=reject_reasons,
                    metadata_snapshot=ev.metadata_snapshot,
                    venue_score=score,
                    expected_cost=cost,
                    execution_permitted=ev.execution_permitted,
                    evidence=ev.evidence,
                )
            )

        return RouteDecision(
            symbol=symbol,
            outcome=RouteDecisionOutcome.ROUTE_TO_VENUE,
            selected_venue=selected,
            selected_cost_bps=recommendation.recommended_cost_bps,
            routing_recommendation=recommendation,
            venue_evaluations=tuple(final_evals),
            reason=f"routed:{selected}",
            decided_at_ns=time.time_ns(),
            evidence={
                "eligible_count": len(eligible_venues),
                "total_count": len(venue_metadata),
                "selected_venue": selected,
                "selected_cost_bps": recommendation.recommended_cost_bps,
            },
        )
