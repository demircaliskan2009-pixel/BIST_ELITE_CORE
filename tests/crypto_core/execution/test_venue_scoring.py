"""Tests for venue scoring and routing intelligence — Phase 9A.

Covers:
  - VenueStatus enum values
  - VenueBlockReason enum values
  - VenueScoreComponents frozen invariant
  - VenueScoringEngine composite score calculation
  - VenueScoringEngine status thresholds (PREFERRED/AVAILABLE/DEGRADED/BLOCKED)
  - VenueScoringEngine explicit block override
  - VenueScoringEngine missing-data penalty
  - VenueScoringEngine weight validation
  - VenueFeeSchedule defaults
  - ExpectedCostCalculator with known and unknown venues
  - ExpectedCostCalculator venue risk adjustments
  - RoutingEngine single venue → ROUTE
  - RoutingEngine multi-venue → lowest cost
  - RoutingEngine all blocked → ABSTAIN
  - RoutingEngine empty venues → ABSTAIN
  - RoutingAction enum values
"""

from __future__ import annotations

import math

import pytest

from crypto_core.execution.venue_scoring import (
    DEFAULT_FEE_SCHEDULES,
    DEFAULT_VENUE_WEIGHTS,
    MISSING_DATA_PENALTY_SCORE,
    ExpectedCostCalculator,
    RoutingAction,
    RoutingEngine,
    VenueBlockReason,
    VenueScoreComponents,
    VenueScoringConfig,
    VenueScoringEngine,
    VenueStatus,
)

# ===================================================================
# Enum tests
# ===================================================================


class TestVenueStatus:
    def test_values(self) -> None:
        assert VenueStatus.PREFERRED.value == "preferred"
        assert VenueStatus.AVAILABLE.value == "available"
        assert VenueStatus.DEGRADED.value == "degraded"
        assert VenueStatus.BLOCKED.value == "blocked"
        assert VenueStatus.UNKNOWN.value == "unknown"


class TestVenueBlockReason:
    def test_values(self) -> None:
        assert VenueBlockReason.OUTAGE.value == "outage"
        assert VenueBlockReason.MAINTENANCE.value == "maintenance"
        assert VenueBlockReason.NONE.value == "none"


class TestRoutingAction:
    def test_values(self) -> None:
        assert RoutingAction.ROUTE.value == "route"
        assert RoutingAction.ABSTAIN.value == "abstain"


# ===================================================================
# VenueScoreComponents tests
# ===================================================================


class TestVenueScoreComponents:
    def test_defaults_all_none(self) -> None:
        c = VenueScoreComponents()
        assert c.execution_quality is None
        assert c.spread_depth_quality is None
        assert c.fee_score is None

    def test_frozen(self) -> None:
        c = VenueScoreComponents(execution_quality=0.8)
        with pytest.raises(AttributeError):
            c.execution_quality = 0.9  # type: ignore[misc]


# ===================================================================
# Default weights tests
# ===================================================================


class TestDefaultWeights:
    def test_sum_to_one(self) -> None:
        total = sum(DEFAULT_VENUE_WEIGHTS.values())
        assert abs(total - 1.0) < 0.001

    def test_all_positive(self) -> None:
        for w in DEFAULT_VENUE_WEIGHTS.values():
            assert w > 0.0


class TestDefaultFeeSchedules:
    def test_known_venues(self) -> None:
        assert "binance" in DEFAULT_FEE_SCHEDULES
        assert "bybit" in DEFAULT_FEE_SCHEDULES
        assert DEFAULT_FEE_SCHEDULES["binance"].taker_fee_bps > 0


# ===================================================================
# VenueScoringEngine tests
# ===================================================================


class TestVenueScoringEngine:
    def _engine(self) -> VenueScoringEngine:
        return VenueScoringEngine()

    def test_all_perfect_scores_preferred(self) -> None:
        engine = self._engine()
        components = VenueScoreComponents(
            execution_quality=1.0,
            spread_depth_quality=1.0,
            fee_score=1.0,
            funding_fairness=1.0,
            reliability=1.0,
            liquidation_design_risk=1.0,
            manipulation_risk=1.0,
            regulatory_availability=1.0,
        )
        score = engine.score_venue("binance", "BTCUSDT", components)
        assert score.composite_score >= 0.99
        assert score.status == VenueStatus.PREFERRED

    def test_all_zero_scores_blocked(self) -> None:
        engine = self._engine()
        components = VenueScoreComponents(
            execution_quality=0.0,
            spread_depth_quality=0.0,
            fee_score=0.0,
            funding_fairness=0.0,
            reliability=0.0,
            liquidation_design_risk=0.0,
            manipulation_risk=0.0,
            regulatory_availability=0.0,
        )
        score = engine.score_venue("test", "BTCUSDT", components)
        assert score.composite_score < 0.01
        assert score.status == VenueStatus.BLOCKED

    def test_missing_data_penalty(self) -> None:
        engine = self._engine()
        # All None → all get penalty score
        components = VenueScoreComponents()
        score = engine.score_venue("test", "BTCUSDT", components)
        # Score should be around MISSING_DATA_PENALTY_SCORE
        assert abs(score.composite_score - MISSING_DATA_PENALTY_SCORE) < 0.01

    def test_explicit_block_overrides_score(self) -> None:
        engine = self._engine()
        components = VenueScoreComponents(
            execution_quality=1.0,
            spread_depth_quality=1.0,
            fee_score=1.0,
            funding_fairness=1.0,
            reliability=1.0,
            liquidation_design_risk=1.0,
            manipulation_risk=1.0,
            regulatory_availability=1.0,
        )
        score = engine.score_venue(
            "binance",
            "BTCUSDT",
            components,
            block_reason=VenueBlockReason.OUTAGE,
        )
        assert score.status == VenueStatus.BLOCKED
        assert score.composite_score == 0.0
        assert score.block_reason == VenueBlockReason.OUTAGE

    def test_mid_range_available(self) -> None:
        engine = self._engine()
        components = VenueScoreComponents(
            execution_quality=0.6,
            spread_depth_quality=0.6,
            fee_score=0.6,
            funding_fairness=0.6,
            reliability=0.6,
            liquidation_design_risk=0.6,
            manipulation_risk=0.6,
            regulatory_availability=0.6,
        )
        score = engine.score_venue("test", "BTCUSDT", components)
        assert score.status == VenueStatus.AVAILABLE
        assert 0.5 <= score.composite_score < 0.75

    def test_weight_validation_fails(self) -> None:
        bad_weights = {"execution_quality": 0.5, "spread_depth_quality": 0.6}
        with pytest.raises(ValueError, match="weights must sum to 1.0"):
            VenueScoringEngine(VenueScoringConfig(weights=bad_weights))

    def test_score_has_evidence(self) -> None:
        engine = self._engine()
        components = VenueScoreComponents(execution_quality=0.8)
        score = engine.score_venue("binance", "BTCUSDT", components)
        assert "components" in score.evidence
        assert score.computed_at_ns > 0


# ===================================================================
# ExpectedCostCalculator tests
# ===================================================================


class TestExpectedCostCalculator:
    def _calc(self) -> ExpectedCostCalculator:
        return ExpectedCostCalculator()

    def test_taker_cost_binance(self) -> None:
        calc = self._calc()
        cost = calc.estimate(
            venue="binance",
            symbol="BTCUSDT",
            half_spread_bps=3.0,
            expected_impact_bps=1.0,
            is_maker=False,
        )
        # taker fee = 5.0 bps (binance default)
        # total = 3.0 + 1.0 + 5.0 + 0.0 + risk_adj
        assert cost.fee_bps == 5.0
        assert cost.total_expected_cost_bps > 9.0

    def test_maker_cost_binance(self) -> None:
        calc = self._calc()
        cost = calc.estimate(
            venue="binance",
            symbol="BTCUSDT",
            half_spread_bps=3.0,
            expected_impact_bps=0.5,
            is_maker=True,
        )
        assert cost.fee_bps == 2.0  # maker fee
        assert cost.fill_role_assumed == "maker"

    def test_unknown_venue_conservative_fee(self) -> None:
        calc = self._calc()
        cost = calc.estimate(
            venue="unknown_exchange",
            symbol="BTCUSDT",
            half_spread_bps=5.0,
            expected_impact_bps=2.0,
            is_maker=False,
        )
        # Unknown venue → 6.0 bps conservative
        assert cost.fee_bps == 6.0
        assert cost.evidence["fee_source"] == "default_conservative"

    def test_preferred_venue_no_risk_adj(self) -> None:
        calc = self._calc()
        engine = VenueScoringEngine()
        components = VenueScoreComponents(
            execution_quality=1.0,
            spread_depth_quality=1.0,
            fee_score=1.0,
            funding_fairness=1.0,
            reliability=1.0,
            liquidation_design_risk=1.0,
            manipulation_risk=1.0,
            regulatory_availability=1.0,
        )
        vs = engine.score_venue("binance", "BTCUSDT", components)
        assert vs.status == VenueStatus.PREFERRED

        cost = calc.estimate(
            venue="binance",
            symbol="BTCUSDT",
            half_spread_bps=2.0,
            expected_impact_bps=1.0,
            is_maker=False,
            venue_score=vs,
        )
        assert cost.venue_risk_adjustment_bps == 0.0

    def test_blocked_venue_inf_risk_adj(self) -> None:
        calc = self._calc()
        engine = VenueScoringEngine()
        components = VenueScoreComponents()
        vs = engine.score_venue(
            "test",
            "BTCUSDT",
            components,
            block_reason=VenueBlockReason.OUTAGE,
        )
        cost = calc.estimate(
            venue="test",
            symbol="BTCUSDT",
            half_spread_bps=2.0,
            expected_impact_bps=1.0,
            is_maker=False,
            venue_score=vs,
        )
        assert math.isinf(cost.venue_risk_adjustment_bps)
        assert math.isinf(cost.total_expected_cost_bps)


# ===================================================================
# RoutingEngine tests
# ===================================================================


class TestRoutingEngine:
    def _setup(self) -> tuple[VenueScoringEngine, ExpectedCostCalculator, RoutingEngine]:
        se = VenueScoringEngine()
        cc = ExpectedCostCalculator()
        return se, cc, RoutingEngine(se, cc)

    def _good_components(self) -> VenueScoreComponents:
        return VenueScoreComponents(
            execution_quality=0.9,
            spread_depth_quality=0.9,
            fee_score=0.9,
            funding_fairness=0.9,
            reliability=0.9,
            liquidation_design_risk=0.9,
            manipulation_risk=0.9,
            regulatory_availability=0.9,
        )

    def test_single_venue_route(self) -> None:
        _, _, router = self._setup()
        rec = router.recommend(
            symbol="BTCUSDT",
            venue_states={"binance": (self._good_components(), VenueBlockReason.NONE)},
            half_spread_by_venue={"binance": 3.0},
            expected_impact_bps=1.0,
            is_maker=False,
        )
        assert rec.action == RoutingAction.ROUTE
        assert rec.recommended_venue == "binance"
        assert rec.recommended_cost_bps is not None

    def test_multi_venue_lowest_cost_wins(self) -> None:
        _, _, router = self._setup()
        rec = router.recommend(
            symbol="BTCUSDT",
            venue_states={
                "binance": (self._good_components(), VenueBlockReason.NONE),
                "bybit": (self._good_components(), VenueBlockReason.NONE),
            },
            half_spread_by_venue={"binance": 5.0, "bybit": 2.0},
            expected_impact_bps=1.0,
            is_maker=False,
        )
        assert rec.action == RoutingAction.ROUTE
        # bybit has lower spread → lower cost
        assert rec.recommended_venue == "bybit"

    def test_all_blocked_abstain(self) -> None:
        _, _, router = self._setup()
        rec = router.recommend(
            symbol="BTCUSDT",
            venue_states={
                "binance": (self._good_components(), VenueBlockReason.OUTAGE),
                "bybit": (self._good_components(), VenueBlockReason.MAINTENANCE),
            },
            half_spread_by_venue={"binance": 3.0, "bybit": 3.0},
            expected_impact_bps=1.0,
            is_maker=False,
        )
        assert rec.action == RoutingAction.ABSTAIN
        assert rec.recommended_venue is None
        assert rec.reason == "all_venues_blocked"

    def test_empty_venues_abstain(self) -> None:
        _, _, router = self._setup()
        rec = router.recommend(
            symbol="BTCUSDT",
            venue_states={},
            half_spread_by_venue={},
            expected_impact_bps=1.0,
            is_maker=False,
        )
        assert rec.action == RoutingAction.ABSTAIN
        assert rec.reason == "no_venues_provided"

    def test_mixed_blocked_and_available(self) -> None:
        _, _, router = self._setup()
        rec = router.recommend(
            symbol="BTCUSDT",
            venue_states={
                "binance": (self._good_components(), VenueBlockReason.OUTAGE),
                "bybit": (self._good_components(), VenueBlockReason.NONE),
            },
            half_spread_by_venue={"binance": 3.0, "bybit": 3.0},
            expected_impact_bps=1.0,
            is_maker=False,
        )
        assert rec.action == RoutingAction.ROUTE
        assert rec.recommended_venue == "bybit"

    def test_recommendation_has_scores_and_costs(self) -> None:
        _, _, router = self._setup()
        rec = router.recommend(
            symbol="BTCUSDT",
            venue_states={
                "binance": (self._good_components(), VenueBlockReason.NONE),
            },
            half_spread_by_venue={"binance": 3.0},
            expected_impact_bps=1.0,
            is_maker=False,
        )
        assert len(rec.venue_scores) == 1
        assert len(rec.venue_costs) == 1
        assert rec.computed_at_ns > 0
