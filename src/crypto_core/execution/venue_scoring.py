"""Venue scoring and routing intelligence foundation.

Deterministic venue quality framework for multi-exchange routing decisions.
Each venue-symbol pair carries a composite score reflecting execution quality,
spread/depth, fees, funding fairness, reliability, design risk, and
regulatory availability.

Design rules:
  - All models are frozen dataclasses (deterministic, hashable, auditable).
  - Default venue state is UNKNOWN (treated as DEGRADED) — never PREFERRED.
  - BLOCKED venues produce fail-closed NO TRADE.
  - Routing is based on expected all-in cost, not displayed price.
  - Missing data → conservative score (penalize, do not assume quality).
  - All scores are [0.0, 1.0] where 1.0 = best quality.
  - Final score is weighted composite of components.

PRD reference: §7 Execution Engine, Research Memory §5-§6.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class VenueStatus(str, Enum):
    """Operational status of a venue for a given symbol.

    PREFERRED:  Actively route orders here — best quality.
    AVAILABLE:  Usable but not preferred.
    DEGRADED:   Usable with caution, increased slippage assumptions.
    BLOCKED:    Do not route. Temporary (outage) or permanent (regulatory).
    UNKNOWN:    Insufficient data; treat as DEGRADED.
    """

    PREFERRED = "preferred"
    AVAILABLE = "available"
    DEGRADED = "degraded"
    BLOCKED = "blocked"
    UNKNOWN = "unknown"


class VenueBlockReason(str, Enum):
    """Why a venue is BLOCKED."""

    OUTAGE = "outage"
    MAINTENANCE = "maintenance"
    REGULATORY = "regulatory"
    MANIPULATION_DETECTED = "manipulation_detected"
    INSURANCE_DEPLETED = "insurance_depleted"
    OPERATOR_OVERRIDE = "operator_override"
    NONE = "none"


# ---------------------------------------------------------------------------
# Score components
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VenueScoreComponents:
    """Individual score components for a venue-symbol pair.

    All scores are [0.0, 1.0] where 1.0 = best quality.
    None = data unavailable; scoring engine will apply penalty default.
    """

    # Execution quality — derived from TCA markout / slippage history
    execution_quality: float | None = None

    # Spread and depth quality — derived from book snapshots
    spread_depth_quality: float | None = None

    # Fee structure score — lower fees = higher score
    fee_score: float | None = None

    # Funding rate fairness — how close to index
    funding_fairness: float | None = None

    # Reliability — uptime, outage frequency, recovery speed
    reliability: float | None = None

    # Liquidation design risk — mark-price mechanics, ADL aggressiveness
    liquidation_design_risk: float | None = None

    # Manipulation risk prior — wash trading, spoofing detection
    manipulation_risk: float | None = None

    # Regulatory / operational availability — binary-ish but [0, 1]
    regulatory_availability: float | None = None


#: Default weights for composite score calculation.
DEFAULT_VENUE_WEIGHTS: dict[str, float] = {
    "execution_quality": 0.25,
    "spread_depth_quality": 0.20,
    "fee_score": 0.10,
    "funding_fairness": 0.08,
    "reliability": 0.18,
    "liquidation_design_risk": 0.07,
    "manipulation_risk": 0.05,
    "regulatory_availability": 0.07,
}

#: Penalty score applied when a component is None (missing data).
MISSING_DATA_PENALTY_SCORE: float = 0.3


# ---------------------------------------------------------------------------
# Venue score
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VenueScore:
    """Composite venue quality score for a specific venue-symbol pair.

    composite_score: weighted average of components [0.0, 1.0].
    status: derived from composite_score thresholds.
    """

    venue: str
    symbol: str
    composite_score: float
    status: VenueStatus
    components: VenueScoreComponents
    block_reason: VenueBlockReason = VenueBlockReason.NONE
    computed_at_ns: int = 0
    evidence: dict[str, object] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Fee model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VenueFeeSchedule:
    """Fee schedule for a venue.

    All fees in basis points (bps). 10 bps = 0.10%.
    """

    venue: str
    maker_fee_bps: float  # typical range: 0-2 bps
    taker_fee_bps: float  # typical range: 3-7 bps
    # Rebate for maker if applicable (negative fee = rebate)
    maker_rebate_bps: float = 0.0


#: Default fee schedules for known venues.
DEFAULT_FEE_SCHEDULES: dict[str, VenueFeeSchedule] = {
    "binance": VenueFeeSchedule(venue="binance", maker_fee_bps=2.0, taker_fee_bps=5.0),
    "bybit": VenueFeeSchedule(venue="bybit", maker_fee_bps=1.0, taker_fee_bps=5.5),
}


# ---------------------------------------------------------------------------
# Expected cost model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExpectedCostEstimate:
    """Expected all-in cost estimate for executing on a specific venue.

    All values in bps. Total = sum of components.
    """

    venue: str
    symbol: str
    half_spread_bps: float
    expected_impact_bps: float
    fee_bps: float  # maker or taker depending on fill_role
    funding_rate_bps: float
    venue_risk_adjustment_bps: float
    total_expected_cost_bps: float
    fill_role_assumed: str  # "maker" or "taker"
    evidence: dict[str, object] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Routing recommendation
# ---------------------------------------------------------------------------


class RoutingAction(str, Enum):
    """Routing decision outcome."""

    ROUTE = "route"
    ABSTAIN = "abstain"  # All venues blocked or insufficient quality


@dataclass(frozen=True)
class RoutingRecommendation:
    """Routing decision for a specific order.

    If action == ROUTE: recommended_venue is the best venue.
    If action == ABSTAIN: no venue meets quality threshold → NO TRADE.
    """

    symbol: str
    action: RoutingAction
    recommended_venue: str | None  # None if ABSTAIN
    recommended_cost_bps: float | None  # None if ABSTAIN
    venue_costs: tuple[ExpectedCostEstimate, ...] = ()
    venue_scores: tuple[VenueScore, ...] = ()
    reason: str = ""
    computed_at_ns: int = 0


# ---------------------------------------------------------------------------
# Venue scoring engine
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VenueScoringConfig:
    """Configuration for the venue scoring engine.

    preferred_threshold: composite_score >= this → PREFERRED.
    available_threshold: composite_score >= this → AVAILABLE.
    degraded_threshold:  composite_score >= this → DEGRADED.
    Below degraded_threshold → BLOCKED (quality too low).
    """

    weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_VENUE_WEIGHTS))
    missing_penalty: float = MISSING_DATA_PENALTY_SCORE
    preferred_threshold: float = 0.75
    available_threshold: float = 0.50
    degraded_threshold: float = 0.30


class VenueScoringEngine:
    """Deterministic venue quality scoring engine.

    Computes composite scores for venue-symbol pairs from individual
    component scores. Applies missing-data penalties. Derives status
    from threshold classification.

    Usage::

        engine = VenueScoringEngine()
        score = engine.score_venue(
            venue="binance",
            symbol="BTCUSDT",
            components=VenueScoreComponents(execution_quality=0.8, ...),
        )
        assert score.status == VenueStatus.PREFERRED
    """

    def __init__(self, config: VenueScoringConfig | None = None) -> None:
        self._cfg = config or VenueScoringConfig()
        # Validate weights sum to ~1.0
        total_w = sum(self._cfg.weights.values())
        if abs(total_w - 1.0) > 0.01:
            raise ValueError(f"Venue weights must sum to 1.0; got {total_w:.4f}")

    def score_venue(
        self,
        venue: str,
        symbol: str,
        components: VenueScoreComponents,
        *,
        block_reason: VenueBlockReason = VenueBlockReason.NONE,
    ) -> VenueScore:
        """Compute composite venue score.

        If block_reason != NONE → status = BLOCKED regardless of score.
        """
        cfg = self._cfg

        # If explicitly blocked, return immediately
        if block_reason != VenueBlockReason.NONE:
            return VenueScore(
                venue=venue,
                symbol=symbol,
                composite_score=0.0,
                status=VenueStatus.BLOCKED,
                components=components,
                block_reason=block_reason,
                computed_at_ns=time.time_ns(),
                evidence={"blocked_by": block_reason.value},
            )

        # Compute weighted composite
        component_values = {
            "execution_quality": components.execution_quality,
            "spread_depth_quality": components.spread_depth_quality,
            "fee_score": components.fee_score,
            "funding_fairness": components.funding_fairness,
            "reliability": components.reliability,
            "liquidation_design_risk": components.liquidation_design_risk,
            "manipulation_risk": components.manipulation_risk,
            "regulatory_availability": components.regulatory_availability,
        }

        weighted_sum = 0.0
        evidence_components: dict[str, object] = {}
        for key, weight in cfg.weights.items():
            raw = component_values.get(key)
            effective = raw if raw is not None else cfg.missing_penalty
            # Clamp to [0, 1]
            effective = max(0.0, min(1.0, effective))
            weighted_sum += weight * effective
            evidence_components[key] = {
                "raw": raw,
                "effective": round(effective, 4),
                "weight": weight,
                "contribution": round(weight * effective, 4),
            }

        composite = round(weighted_sum, 6)

        # Derive status from thresholds
        if composite >= cfg.preferred_threshold:
            status = VenueStatus.PREFERRED
        elif composite >= cfg.available_threshold:
            status = VenueStatus.AVAILABLE
        elif composite >= cfg.degraded_threshold:
            status = VenueStatus.DEGRADED
        else:
            status = VenueStatus.BLOCKED

        return VenueScore(
            venue=venue,
            symbol=symbol,
            composite_score=composite,
            status=status,
            components=components,
            block_reason=VenueBlockReason.NONE,
            computed_at_ns=time.time_ns(),
            evidence={"components": evidence_components, "composite": composite},
        )


# ---------------------------------------------------------------------------
# Expected cost calculator
# ---------------------------------------------------------------------------


class ExpectedCostCalculator:
    """Calculate expected all-in execution cost for a venue-symbol pair.

    Combines half-spread, expected impact, fee, funding rate, and venue
    risk adjustment into a single expected cost in bps.

    Usage::

        calc = ExpectedCostCalculator()
        cost = calc.estimate(
            venue="binance", symbol="BTCUSDT",
            half_spread_bps=3.0, expected_impact_bps=1.0,
            is_maker=False, funding_rate_bps=0.5,
            venue_score=score,
        )
    """

    def __init__(
        self,
        fee_schedules: dict[str, VenueFeeSchedule] | None = None,
    ) -> None:
        self._fees = fee_schedules or dict(DEFAULT_FEE_SCHEDULES)

    def estimate(
        self,
        *,
        venue: str,
        symbol: str,
        half_spread_bps: float,
        expected_impact_bps: float,
        is_maker: bool,
        funding_rate_bps: float = 0.0,
        venue_score: VenueScore | None = None,
    ) -> ExpectedCostEstimate:
        """Estimate total expected cost for a hypothetical order.

        venue_risk_adjustment_bps: penalty bps derived from venue score.
          PREFERRED → 0 bps, AVAILABLE → 1 bps, DEGRADED → 5 bps,
          BLOCKED → inf (should not be called), UNKNOWN → 5 bps.
        """
        # Fee lookup
        schedule = self._fees.get(venue)
        if schedule is not None:
            fee_bps = schedule.maker_fee_bps if is_maker else schedule.taker_fee_bps
        else:
            # Unknown venue → conservative taker fee assumption
            fee_bps = 6.0

        # Venue risk adjustment
        risk_adj = 5.0  # default for UNKNOWN / DEGRADED
        if venue_score is not None:
            if venue_score.status == VenueStatus.PREFERRED:
                risk_adj = 0.0
            elif venue_score.status == VenueStatus.AVAILABLE:
                risk_adj = 1.0
            elif venue_score.status == VenueStatus.DEGRADED:
                risk_adj = 5.0
            elif venue_score.status == VenueStatus.BLOCKED:
                risk_adj = float("inf")

        total = half_spread_bps + expected_impact_bps + fee_bps + funding_rate_bps + risk_adj

        return ExpectedCostEstimate(
            venue=venue,
            symbol=symbol,
            half_spread_bps=round(half_spread_bps, 4),
            expected_impact_bps=round(expected_impact_bps, 4),
            fee_bps=round(fee_bps, 4),
            funding_rate_bps=round(funding_rate_bps, 4),
            venue_risk_adjustment_bps=round(risk_adj, 4),
            total_expected_cost_bps=round(total, 4),
            fill_role_assumed="maker" if is_maker else "taker",
            evidence={
                "fee_source": "schedule" if schedule is not None else "default_conservative",
                "risk_adj_source": venue_score.status.value if venue_score else "no_score",
            },
        )


# ---------------------------------------------------------------------------
# Routing engine
# ---------------------------------------------------------------------------


class RoutingEngine:
    """Deterministic routing engine — selects venue by lowest expected cost.

    Fail-closed: if no venue is routable → ABSTAIN (NO TRADE).

    Usage::

        router = RoutingEngine(scoring_engine, cost_calculator)
        rec = router.recommend(
            symbol="BTCUSDT",
            venue_states={
                "binance": (components_b, VenueBlockReason.NONE),
                "bybit": (components_by, VenueBlockReason.NONE),
            },
            half_spread_by_venue={"binance": 2.5, "bybit": 3.0},
            expected_impact_bps=1.0,
            is_maker=False,
        )
        if rec.action == RoutingAction.ROUTE:
            # route to rec.recommended_venue
        else:
            # NO TRADE
    """

    def __init__(
        self,
        scoring_engine: VenueScoringEngine,
        cost_calculator: ExpectedCostCalculator,
    ) -> None:
        self._scorer = scoring_engine
        self._cost_calc = cost_calculator

    def recommend(
        self,
        *,
        symbol: str,
        venue_states: dict[str, tuple[VenueScoreComponents, VenueBlockReason]],
        half_spread_by_venue: dict[str, float],
        expected_impact_bps: float,
        is_maker: bool,
        funding_rate_by_venue: dict[str, float] | None = None,
    ) -> RoutingRecommendation:
        """Produce a routing recommendation for a symbol across venues.

        venue_states: dict mapping venue_name → (components, block_reason).
        half_spread_by_venue: current half-spread in bps per venue.
        funding_rate_by_venue: optional current funding rate bps per venue.

        Returns RoutingRecommendation with ROUTE or ABSTAIN.
        """
        if not venue_states:
            return RoutingRecommendation(
                symbol=symbol,
                action=RoutingAction.ABSTAIN,
                recommended_venue=None,
                recommended_cost_bps=None,
                reason="no_venues_provided",
                computed_at_ns=time.time_ns(),
            )

        funding = funding_rate_by_venue or {}
        scores: list[VenueScore] = []
        costs: list[ExpectedCostEstimate] = []

        for venue, (components, block_reason) in venue_states.items():
            score = self._scorer.score_venue(
                venue=venue,
                symbol=symbol,
                components=components,
                block_reason=block_reason,
            )
            scores.append(score)

            if score.status == VenueStatus.BLOCKED:
                continue

            half_spread = half_spread_by_venue.get(venue, 10.0)  # conservative default
            funding_bps = funding.get(venue, 0.0)

            cost = self._cost_calc.estimate(
                venue=venue,
                symbol=symbol,
                half_spread_bps=half_spread,
                expected_impact_bps=expected_impact_bps,
                is_maker=is_maker,
                funding_rate_bps=funding_bps,
                venue_score=score,
            )
            costs.append(cost)

        # Select lowest cost among non-blocked venues
        if not costs:
            return RoutingRecommendation(
                symbol=symbol,
                action=RoutingAction.ABSTAIN,
                recommended_venue=None,
                recommended_cost_bps=None,
                venue_scores=tuple(scores),
                reason="all_venues_blocked",
                computed_at_ns=time.time_ns(),
            )

        best = min(costs, key=lambda c: c.total_expected_cost_bps)

        return RoutingRecommendation(
            symbol=symbol,
            action=RoutingAction.ROUTE,
            recommended_venue=best.venue,
            recommended_cost_bps=best.total_expected_cost_bps,
            venue_costs=tuple(costs),
            venue_scores=tuple(scores),
            reason=f"lowest_cost_{best.venue}",
            computed_at_ns=time.time_ns(),
        )
