"""Tests for live-readiness surface — Phase 9B.

Covers:
  - ReadinessLevel enum values and ordering
  - level_at_least comparison
  - CriterionStatus enum
  - ReadinessCriterion frozen, is_met, is_blocker
  - ReadinessStatus properties: blockers, met_criteria, blocker_names
  - ReadinessEvaluator: conservative level determination
  - Research-only: when only research criteria met
  - Paper-live: when all paper criteria met
  - NOT_ASSESSED: when nothing is met
  - Unknown criteria block promotion
  - Serialization round-trip
  - Fail-closed on malformed dict
"""

from __future__ import annotations

import pytest

from crypto_core.service.readiness import (
    CriterionStatus,
    ReadinessCriterion,
    ReadinessEvaluator,
    ReadinessEvaluatorConfig,
    ReadinessLevel,
    ReadinessStatus,
    level_at_least,
    readiness_from_dict,
    readiness_to_dict,
)


class TestReadinessLevel:
    def test_values(self) -> None:
        assert ReadinessLevel.NOT_ASSESSED.value == "not_assessed"
        assert ReadinessLevel.RESEARCH_ONLY.value == "research_only"
        assert ReadinessLevel.PAPER_LIVE.value == "paper_live"
        assert ReadinessLevel.TINY_CAP_LIVE.value == "tiny_cap_live"

    def test_level_at_least_equal(self) -> None:
        assert (
            level_at_least(
                ReadinessLevel.PAPER_LIVE,
                ReadinessLevel.PAPER_LIVE,
            )
            is True
        )

    def test_level_at_least_above(self) -> None:
        assert (
            level_at_least(
                ReadinessLevel.SHADOW_LIVE,
                ReadinessLevel.PAPER_LIVE,
            )
            is True
        )

    def test_level_at_least_below(self) -> None:
        assert (
            level_at_least(
                ReadinessLevel.RESEARCH_ONLY,
                ReadinessLevel.PAPER_LIVE,
            )
            is False
        )


class TestCriterion:
    def test_frozen(self) -> None:
        c = ReadinessCriterion(
            name="test",
            description="test criterion",
            status=CriterionStatus.MET,
        )
        with pytest.raises(AttributeError):
            c.status = CriterionStatus.NOT_MET  # type: ignore[misc]

    def test_is_met(self) -> None:
        c = ReadinessCriterion(
            name="test",
            description="test",
            status=CriterionStatus.MET,
        )
        assert c.is_met is True
        assert c.is_blocker is False

    def test_is_blocker(self) -> None:
        c = ReadinessCriterion(
            name="test",
            description="test",
            status=CriterionStatus.NOT_MET,
            blocker_reason="not configured",
        )
        assert c.is_blocker is True
        assert c.is_met is False


class TestReadinessStatus:
    def test_blockers(self) -> None:
        criteria = (
            ReadinessCriterion(name="a", description="a", status=CriterionStatus.MET),
            ReadinessCriterion(
                name="b",
                description="b",
                status=CriterionStatus.NOT_MET,
                blocker_reason="missing",
            ),
        )
        status = ReadinessStatus(
            level=ReadinessLevel.NOT_ASSESSED,
            criteria=criteria,
            assessed_at_ns=1_000_000,
        )
        assert len(status.blockers) == 1
        assert status.blocker_names == ["b"]
        assert len(status.met_criteria) == 1

    def test_is_paper_ready(self) -> None:
        status = ReadinessStatus(
            level=ReadinessLevel.PAPER_LIVE,
            criteria=(),
            assessed_at_ns=1_000_000,
        )
        assert status.is_paper_ready is True
        assert status.is_live_ready is False

    def test_is_live_ready(self) -> None:
        status = ReadinessStatus(
            level=ReadinessLevel.TINY_CAP_LIVE,
            criteria=(),
            assessed_at_ns=1_000_000,
        )
        assert status.is_live_ready is True


class TestReadinessEvaluator:
    def test_not_assessed_when_nothing_met(self) -> None:
        evaluator = ReadinessEvaluator()
        status = evaluator.evaluate(flags={}, assessed_at_ns=1_000_000)
        assert status.level == ReadinessLevel.NOT_ASSESSED

    def test_research_only(self) -> None:
        evaluator = ReadinessEvaluator()
        flags = {
            "execution_engine_initialized": True,
            "edge_definitions_loaded": True,
            "backtest_data_available": True,
        }
        status = evaluator.evaluate(flags=flags, assessed_at_ns=1_000_000)
        assert status.level == ReadinessLevel.RESEARCH_ONLY

    def test_paper_live(self) -> None:
        evaluator = ReadinessEvaluator()
        flags = {
            "execution_engine_initialized": True,
            "edge_definitions_loaded": True,
            "backtest_data_available": True,
            "live_data_feed_connected": True,
            "order_book_valid": True,
            "fill_pricer_configured": True,
            "system_state_engine_running": True,
            "evidence_store_writable": True,
            "execution_intelligence_active": True,
        }
        status = evaluator.evaluate(flags=flags, assessed_at_ns=1_000_000)
        assert status.level == ReadinessLevel.PAPER_LIVE

    def test_unknown_blocks_promotion(self) -> None:
        evaluator = ReadinessEvaluator()
        flags = {
            "execution_engine_initialized": True,
            "edge_definitions_loaded": True,
            "backtest_data_available": None,  # unknown → blocks
        }
        status = evaluator.evaluate(flags=flags, assessed_at_ns=1_000_000)
        assert status.level == ReadinessLevel.NOT_ASSESSED

    def test_false_blocks_promotion(self) -> None:
        evaluator = ReadinessEvaluator()
        flags = {
            "execution_engine_initialized": True,
            "edge_definitions_loaded": True,
            "backtest_data_available": False,
        }
        status = evaluator.evaluate(flags=flags, assessed_at_ns=1_000_000)
        assert status.level == ReadinessLevel.NOT_ASSESSED

    def test_criteria_overrides(self) -> None:
        config = ReadinessEvaluatorConfig(
            criteria_overrides={"backtest_data_available": CriterionStatus.MET},
        )
        evaluator = ReadinessEvaluator(config)
        flags = {
            "execution_engine_initialized": True,
            "edge_definitions_loaded": True,
            # backtest_data_available is overridden to MET
        }
        status = evaluator.evaluate(flags=flags, assessed_at_ns=1_000_000)
        assert status.level == ReadinessLevel.RESEARCH_ONLY

    def test_full_live_readiness(self) -> None:
        evaluator = ReadinessEvaluator()
        flags = {
            "execution_engine_initialized": True,
            "edge_definitions_loaded": True,
            "backtest_data_available": True,
            "live_data_feed_connected": True,
            "order_book_valid": True,
            "fill_pricer_configured": True,
            "system_state_engine_running": True,
            "evidence_store_writable": True,
            "execution_intelligence_active": True,
            "paper_campaign_completed": True,
            "paper_fill_calibration_available": True,
            "tca_records_sufficient": True,
            "venue_metadata_live": True,
            "routing_engine_configured": True,
            "risk_limits_set": True,
            "kill_switch_tested": True,
            "live_api_credentials_valid": True,
            "margin_requirements_verified": True,
            "canary_allocation_set": True,
            "operator_approval_recorded": True,
        }
        status = evaluator.evaluate(flags=flags, assessed_at_ns=1_000_000)
        assert status.level == ReadinessLevel.TINY_CAP_LIVE
        assert status.is_live_ready is True
        assert len(status.blockers) == 0


class TestReadinessSerialization:
    def test_round_trip(self) -> None:
        evaluator = ReadinessEvaluator()
        flags = {
            "execution_engine_initialized": True,
            "edge_definitions_loaded": True,
            "backtest_data_available": True,
        }
        original = evaluator.evaluate(flags=flags, assessed_at_ns=1_000_000)
        d = readiness_to_dict(original)
        restored = readiness_from_dict(d)

        assert restored.level == original.level
        assert restored.assessed_at_ns == original.assessed_at_ns
        assert len(restored.criteria) == len(original.criteria)

    def test_malformed_raises(self) -> None:
        with pytest.raises(ValueError, match="Malformed"):
            readiness_from_dict({"bad": "data"})
