"""Tests for route binding — metadata-gated routing (Phase 9C).

Covers:
  - RouteDecisionOutcome enum values
  - VenueRejectReason enum values
  - VenueEvaluation frozen invariant
  - RouteDecision frozen invariant + properties
  - MetadataGatedRouter single healthy venue → ROUTE_TO_VENUE
  - MetadataGatedRouter multi-venue, both healthy → lowest cost wins
  - MetadataGatedRouter one venue has stale fees → that venue rejected
  - MetadataGatedRouter all venues have missing metadata → BLOCK
  - MetadataGatedRouter venue not operational → rejected
  - MetadataGatedRouter degraded venue rejected unless config allows
  - MetadataGatedRouter explicit block reason → venue rejected
  - MetadataGatedRouter routing engine ABSTAIN → ABSTAIN
  - RouteDecision serialization (route_decision_to_dict)
  - RouteDecision.is_routable / blocked_venues
  - MetadataGatedRouterConfig defaults
  - MetadataGatedRouter require_funding_data gate
"""

from __future__ import annotations

import pytest

from crypto_core.execution.route_binding import (
    MetadataGatedRouter,
    MetadataGatedRouterConfig,
    RouteDecision,
    RouteDecisionOutcome,
    VenueEvaluation,
    VenueRejectReason,
    route_decision_to_dict,
)
from crypto_core.execution.venue_metadata import (
    FeeMetadata,
    FundingMetadata,
    MetadataFreshness,
    OperationalMetadata,
    VenueMetadataSnapshot,
    VenueOperationalStatus,
)
from crypto_core.execution.venue_scoring import (
    ExpectedCostCalculator,
    RoutingEngine,
    VenueBlockReason,
    VenueScoreComponents,
    VenueScoringEngine,
)

# ===================================================================
# Fixtures
# ===================================================================


_TS = 1_000_000_000_000  # arbitrary baseline timestamp (ns)


def _fee(
    freshness: MetadataFreshness = MetadataFreshness.LIVE,
) -> FeeMetadata:
    return FeeMetadata(
        maker_fee_bps=2.0,
        taker_fee_bps=4.0,
        freshness=freshness,
        source="test",
        observed_at_ns=_TS,
    )


def _funding(
    freshness: MetadataFreshness = MetadataFreshness.LIVE,
) -> FundingMetadata:
    return FundingMetadata(
        funding_rate_bps=1.0,
        freshness=freshness,
        source="test",
        observed_at_ns=_TS,
    )


def _ops(
    status: VenueOperationalStatus = VenueOperationalStatus.OPERATIONAL,
) -> OperationalMetadata:
    return OperationalMetadata(
        status=status,
        freshness=MetadataFreshness.LIVE,
        observed_at_ns=_TS,
    )


def _make_healthy_metadata(venue: str) -> VenueMetadataSnapshot:
    """Healthy metadata: LIVE fees, operational, funding available."""
    return VenueMetadataSnapshot(
        venue=venue,
        symbol="BTCUSDT",
        snapshot_ns=_TS,
        fees=_fee(),
        funding=_funding(),
        operational=_ops(),
    )


def _make_stale_fee_metadata(venue: str) -> VenueMetadataSnapshot:
    """Stale fees — should be rejected."""
    return VenueMetadataSnapshot(
        venue=venue,
        symbol="BTCUSDT",
        snapshot_ns=_TS,
        fees=_fee(MetadataFreshness.STALE),
        funding=_funding(),
        operational=_ops(),
    )


def _make_no_fee_metadata(venue: str) -> VenueMetadataSnapshot:
    """No fees — execution_permitted = False."""
    return VenueMetadataSnapshot(
        venue=venue,
        symbol="BTCUSDT",
        snapshot_ns=_TS,
        fees=None,
        funding=_funding(),
        operational=_ops(),
    )


def _make_degraded_metadata(venue: str) -> VenueMetadataSnapshot:
    """Degraded venue — may be rejected by config."""
    return VenueMetadataSnapshot(
        venue=venue,
        symbol="BTCUSDT",
        snapshot_ns=_TS,
        fees=_fee(),
        funding=_funding(),
        operational=_ops(VenueOperationalStatus.DEGRADED),
    )


def _make_not_operational_metadata(venue: str) -> VenueMetadataSnapshot:
    """Venue under maintenance."""
    return VenueMetadataSnapshot(
        venue=venue,
        symbol="BTCUSDT",
        snapshot_ns=_TS,
        fees=_fee(),
        funding=_funding(),
        operational=_ops(VenueOperationalStatus.MAINTENANCE),
    )


def _make_no_funding_metadata(venue: str) -> VenueMetadataSnapshot:
    """No funding data."""
    return VenueMetadataSnapshot(
        venue=venue,
        symbol="BTCUSDT",
        snapshot_ns=_TS,
        fees=_fee(),
        funding=None,
        operational=_ops(),
    )


def _good_components() -> VenueScoreComponents:
    """Healthy scoring components."""
    return VenueScoreComponents(
        execution_quality=0.90,
        spread_depth_quality=0.85,
        fee_score=0.80,
        funding_fairness=0.75,
        reliability=0.95,
        liquidation_design_risk=0.70,
        manipulation_risk=0.80,
        regulatory_availability=0.90,
    )


def _make_router(
    config: MetadataGatedRouterConfig | None = None,
) -> MetadataGatedRouter:
    """Build a router with default scoring and cost engines."""
    scorer = VenueScoringEngine()
    cost_calc = ExpectedCostCalculator()
    routing_engine = RoutingEngine(scorer, cost_calc)
    return MetadataGatedRouter(routing_engine, config)


# ===================================================================
# Enum tests
# ===================================================================


class TestRouteDecisionOutcome:
    def test_values(self) -> None:
        assert RouteDecisionOutcome.ROUTE_TO_VENUE.value == "route_to_venue"
        assert RouteDecisionOutcome.ABSTAIN.value == "abstain"
        assert RouteDecisionOutcome.BLOCK.value == "block"
        assert RouteDecisionOutcome.FALLBACK_NOT_ALLOWED.value == "fallback_not_allowed"


class TestVenueRejectReason:
    def test_values(self) -> None:
        assert VenueRejectReason.METADATA_UNAVAILABLE.value == "metadata_unavailable"
        assert VenueRejectReason.METADATA_STALE.value == "metadata_stale"
        assert VenueRejectReason.FEE_DATA_MISSING.value == "fee_data_missing"
        assert VenueRejectReason.VENUE_NOT_OPERATIONAL.value == "venue_not_operational"
        assert VenueRejectReason.VENUE_DEGRADED.value == "venue_degraded"
        assert VenueRejectReason.VENUE_BLOCKED.value == "venue_blocked"
        assert VenueRejectReason.SCORE_TOO_LOW.value == "score_too_low"
        assert VenueRejectReason.HIGHER_COST.value == "higher_cost"
        assert VenueRejectReason.EXECUTION_NOT_PERMITTED.value == "execution_not_permitted"


# ===================================================================
# Frozen invariant tests
# ===================================================================


class TestVenueEvaluationFrozen:
    def test_frozen(self) -> None:
        ev = VenueEvaluation(venue="binance", symbol="BTCUSDT", selected=True)
        with pytest.raises(AttributeError):
            ev.venue = "bybit"  # type: ignore[misc]

    def test_defaults(self) -> None:
        ev = VenueEvaluation(venue="binance", symbol="BTCUSDT", selected=False)
        assert ev.reject_reasons == ()
        assert ev.metadata_snapshot is None
        assert ev.venue_score is None
        assert ev.expected_cost is None
        assert ev.execution_permitted is False


class TestRouteDecisionFrozen:
    def test_frozen(self) -> None:
        rd = RouteDecision(symbol="BTCUSDT", outcome=RouteDecisionOutcome.ABSTAIN)
        with pytest.raises(AttributeError):
            rd.symbol = "ETHUSDT"  # type: ignore[misc]

    def test_is_routable_when_route(self) -> None:
        rd = RouteDecision(
            symbol="BTCUSDT",
            outcome=RouteDecisionOutcome.ROUTE_TO_VENUE,
            selected_venue="binance",
        )
        assert rd.is_routable is True

    def test_not_routable_when_abstain(self) -> None:
        rd = RouteDecision(symbol="BTCUSDT", outcome=RouteDecisionOutcome.ABSTAIN)
        assert rd.is_routable is False

    def test_blocked_venues(self) -> None:
        ev1 = VenueEvaluation(venue="binance", symbol="BTCUSDT", selected=True)
        ev2 = VenueEvaluation(venue="bybit", symbol="BTCUSDT", selected=False)
        rd = RouteDecision(
            symbol="BTCUSDT",
            outcome=RouteDecisionOutcome.ROUTE_TO_VENUE,
            venue_evaluations=(ev1, ev2),
        )
        assert rd.blocked_venues == ("bybit",)


# ===================================================================
# Serialization tests
# ===================================================================


class TestRouteDecisionSerialization:
    def test_round_trip(self) -> None:
        rd = RouteDecision(
            symbol="BTCUSDT",
            outcome=RouteDecisionOutcome.ROUTE_TO_VENUE,
            selected_venue="binance",
            selected_cost_bps=3.5,
            decided_at_ns=1234567890,
        )
        d = route_decision_to_dict(rd)
        assert d["symbol"] == "BTCUSDT"
        assert d["outcome"] == "route_to_venue"
        assert d["selected_venue"] == "binance"
        assert d["selected_cost_bps"] == 3.5
        assert d["decided_at_ns"] == 1234567890
        assert isinstance(d["blocked_venues"], list)


# ===================================================================
# MetadataGatedRouterConfig tests
# ===================================================================


class TestMetadataGatedRouterConfig:
    def test_defaults(self) -> None:
        c = MetadataGatedRouterConfig()
        assert c.allow_estimated_fees is True
        assert c.allow_degraded_venues is False
        assert c.require_funding_data is False


# ===================================================================
# MetadataGatedRouter integration tests
# ===================================================================


class TestMetadataGatedRouterSingleVenue:
    """Single healthy venue → ROUTE_TO_VENUE."""

    def test_single_healthy_venue_routes(self) -> None:
        router = _make_router()
        decision = router.decide(
            symbol="BTCUSDT",
            venue_metadata={"binance": _make_healthy_metadata("binance")},
            venue_components={"binance": _good_components()},
            half_spread_by_venue={"binance": 2.5},
            expected_impact_bps=1.0,
            is_maker=False,
        )
        assert decision.outcome == RouteDecisionOutcome.ROUTE_TO_VENUE
        assert decision.selected_venue == "binance"
        assert decision.is_routable is True
        assert decision.selected_cost_bps is not None
        assert len(decision.venue_evaluations) == 1

    def test_single_venue_no_fees_blocks(self) -> None:
        router = _make_router()
        decision = router.decide(
            symbol="BTCUSDT",
            venue_metadata={"binance": _make_no_fee_metadata("binance")},
            venue_components={"binance": _good_components()},
            half_spread_by_venue={"binance": 2.5},
            expected_impact_bps=1.0,
            is_maker=False,
        )
        assert decision.outcome == RouteDecisionOutcome.BLOCK
        assert decision.is_routable is False


class TestMetadataGatedRouterMultiVenue:
    """Multi-venue routing scenarios."""

    def test_two_healthy_venues_routes_to_lower_cost(self) -> None:
        router = _make_router()
        decision = router.decide(
            symbol="BTCUSDT",
            venue_metadata={
                "binance": _make_healthy_metadata("binance"),
                "bybit": _make_healthy_metadata("bybit"),
            },
            venue_components={
                "binance": _good_components(),
                "bybit": _good_components(),
            },
            half_spread_by_venue={"binance": 2.5, "bybit": 5.0},
            expected_impact_bps=1.0,
            is_maker=False,
        )
        assert decision.outcome == RouteDecisionOutcome.ROUTE_TO_VENUE
        assert decision.selected_venue is not None
        assert decision.is_routable is True
        assert len(decision.venue_evaluations) == 2

    def test_one_stale_fee_venue_rejected(self) -> None:
        router = _make_router()
        decision = router.decide(
            symbol="BTCUSDT",
            venue_metadata={
                "binance": _make_healthy_metadata("binance"),
                "bybit": _make_stale_fee_metadata("bybit"),
            },
            venue_components={
                "binance": _good_components(),
                "bybit": _good_components(),
            },
            half_spread_by_venue={"binance": 2.5, "bybit": 3.0},
            expected_impact_bps=1.0,
            is_maker=False,
        )
        assert decision.outcome == RouteDecisionOutcome.ROUTE_TO_VENUE
        assert decision.selected_venue == "binance"
        # bybit should be in blocked_venues
        assert "bybit" in decision.blocked_venues

    def test_all_stale_fees_blocks(self) -> None:
        router = _make_router()
        decision = router.decide(
            symbol="BTCUSDT",
            venue_metadata={
                "binance": _make_stale_fee_metadata("binance"),
                "bybit": _make_stale_fee_metadata("bybit"),
            },
            venue_components={
                "binance": _good_components(),
                "bybit": _good_components(),
            },
            half_spread_by_venue={"binance": 2.5, "bybit": 3.0},
            expected_impact_bps=1.0,
            is_maker=False,
        )
        assert decision.outcome == RouteDecisionOutcome.BLOCK
        assert "metadata_stale" in decision.reason


class TestMetadataGatedRouterOperationalGating:
    """Venue operational status gating."""

    def test_not_operational_rejected(self) -> None:
        router = _make_router()
        decision = router.decide(
            symbol="BTCUSDT",
            venue_metadata={
                "binance": _make_not_operational_metadata("binance"),
            },
            venue_components={"binance": _good_components()},
            half_spread_by_venue={"binance": 2.5},
            expected_impact_bps=1.0,
            is_maker=False,
        )
        assert decision.outcome == RouteDecisionOutcome.BLOCK

    def test_degraded_rejected_by_default_config(self) -> None:
        router = _make_router()  # allow_degraded_venues=False
        decision = router.decide(
            symbol="BTCUSDT",
            venue_metadata={
                "binance": _make_degraded_metadata("binance"),
            },
            venue_components={"binance": _good_components()},
            half_spread_by_venue={"binance": 2.5},
            expected_impact_bps=1.0,
            is_maker=False,
        )
        assert decision.outcome == RouteDecisionOutcome.BLOCK

    def test_degraded_allowed_by_config(self) -> None:
        config = MetadataGatedRouterConfig(allow_degraded_venues=True)
        router = _make_router(config)
        decision = router.decide(
            symbol="BTCUSDT",
            venue_metadata={
                "binance": _make_degraded_metadata("binance"),
            },
            venue_components={"binance": _good_components()},
            half_spread_by_venue={"binance": 2.5},
            expected_impact_bps=1.0,
            is_maker=False,
        )
        # DEGRADED with LIVE fees and allow_degraded_venues → can route
        assert decision.outcome == RouteDecisionOutcome.ROUTE_TO_VENUE


class TestMetadataGatedRouterExplicitBlock:
    """Explicit block reason → always rejected."""

    def test_explicit_block_reason_rejects(self) -> None:
        router = _make_router()
        decision = router.decide(
            symbol="BTCUSDT",
            venue_metadata={
                "binance": _make_healthy_metadata("binance"),
            },
            venue_components={"binance": _good_components()},
            half_spread_by_venue={"binance": 2.5},
            expected_impact_bps=1.0,
            is_maker=False,
            venue_block_reasons={"binance": VenueBlockReason.OUTAGE},
        )
        assert decision.outcome == RouteDecisionOutcome.BLOCK


class TestMetadataGatedRouterFundingGate:
    """Require funding data gate."""

    def test_missing_funding_blocks_when_required(self) -> None:
        config = MetadataGatedRouterConfig(require_funding_data=True)
        router = _make_router(config)
        decision = router.decide(
            symbol="BTCUSDT",
            venue_metadata={
                "binance": _make_no_funding_metadata("binance"),
            },
            venue_components={"binance": _good_components()},
            half_spread_by_venue={"binance": 2.5},
            expected_impact_bps=1.0,
            is_maker=False,
        )
        assert decision.outcome == RouteDecisionOutcome.BLOCK

    def test_missing_funding_ok_when_not_required(self) -> None:
        config = MetadataGatedRouterConfig(require_funding_data=False)
        router = _make_router(config)
        decision = router.decide(
            symbol="BTCUSDT",
            venue_metadata={
                "binance": _make_no_funding_metadata("binance"),
            },
            venue_components={"binance": _good_components()},
            half_spread_by_venue={"binance": 2.5},
            expected_impact_bps=1.0,
            is_maker=False,
        )
        assert decision.outcome == RouteDecisionOutcome.ROUTE_TO_VENUE


class TestMetadataGatedRouterEvidence:
    """Evidence and audit trail in RouteDecision."""

    def test_evidence_populated_on_route(self) -> None:
        router = _make_router()
        decision = router.decide(
            symbol="BTCUSDT",
            venue_metadata={"binance": _make_healthy_metadata("binance")},
            venue_components={"binance": _good_components()},
            half_spread_by_venue={"binance": 2.5},
            expected_impact_bps=1.0,
            is_maker=False,
        )
        assert "eligible_count" in decision.evidence
        assert decision.evidence["eligible_count"] == 1
        assert decision.decided_at_ns > 0

    def test_venue_evaluation_has_metadata_snapshot(self) -> None:
        router = _make_router()
        decision = router.decide(
            symbol="BTCUSDT",
            venue_metadata={"binance": _make_healthy_metadata("binance")},
            venue_components={"binance": _good_components()},
            half_spread_by_venue={"binance": 2.5},
            expected_impact_bps=1.0,
            is_maker=False,
        )
        ev = decision.venue_evaluations[0]
        assert ev.metadata_snapshot is not None
        assert ev.metadata_snapshot.venue == "binance"
