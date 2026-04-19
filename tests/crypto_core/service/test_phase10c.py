"""Tests for Phase 10C — Campaign-to-Promotion Integration + Review Controller.

Covers:
  1.  PromotionReviewController construction (default + custom).
  2.  Review status lifecycle transitions (CREATED → COLLECTING → READY → FINALIZED).
  3.  Campaign intake from completed reports.
  4.  Duplicate campaign handling (reject deterministically).
  5.  Malformed/non-completed campaign rejection.
  6.  Provisional recommendation snapshot.
  7.  Final review report correctness.
  8.  Persistence write/read (workflow state + final review).
  9.  Malformed restore fail-closed.
  10. Deterministic replay / restore.
  11. Readiness interaction truthfulness.
  12. Reporting API views.
  13. Symbol breadth and distribution summaries.

PRD reference: §2 System Orchestration, §7 Execution Engine.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from crypto_core.service.campaign import (
    AcceptanceResult,
    AcceptanceVerdict,
    CampaignReport,
    CampaignSnapshot,
    CriterionResult,
    StabilityRollup,
    SymbolParticipation,
)
from crypto_core.service.evidence_store import (
    EvidenceStore,
    EvidenceStoreConfig,
)
from crypto_core.service.promotion_review import (
    PromotionVerdict,
)
from crypto_core.service.promotion_review_controller import (
    CampaignIntakeError,
    CurrentReviewSnapshot,
    FinalReviewReport,
    PromotionReviewController,
    ReviewStatus,
    ReviewWorkflowCorruptError,
    current_review_snapshot_to_dict,
    final_review_report_to_dict,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_T0_NS = 1_000_000_000_000
_NS_PER_S = 1_000_000_000


# ---------------------------------------------------------------------------
# Helpers — campaign fixtures
# ---------------------------------------------------------------------------


def _make_snapshot(
    *,
    campaign_id: str = "camp-1",
    total_cycles: int = 200,
    total_fills: int = 30,
    total_events: int = 1000,
    symbol_count: int = 3,
    symbols_with_events: int = 3,
    symbols_with_cycles: int = 3,
    elapsed_seconds: float = 600.0,
    blocked_cycles: int = 5,
    failed_cycles: int = 2,
    ei_degraded: bool = False,
    ei_route_blocks: int = 0,
    ei_route_abstains: int = 0,
    recovery_incidents: int = 0,
    stability: StabilityRollup | None = None,
) -> CampaignSnapshot:
    return CampaignSnapshot(
        campaign_id=campaign_id,
        status="completed",
        started_at_ns=_T0_NS,
        updated_at_ns=_T0_NS + int(elapsed_seconds * _NS_PER_S),
        elapsed_seconds=elapsed_seconds,
        run_id="run-1",
        service_mode="running",
        session_mode="running",
        total_events_enqueued=total_events,
        total_events_dropped=0,
        total_cycles=total_cycles,
        approved_cycles=total_cycles - blocked_cycles - failed_cycles,
        blocked_cycles=blocked_cycles,
        failed_cycles=failed_cycles,
        total_fills=total_fills,
        queue_overflows=0,
        watchdog_stalls=0,
        service_restarts=0,
        persistence_failures=0,
        symbol_count=symbol_count,
        symbols_ready=symbol_count,
        symbols_blocked=0,
        symbols_with_events=symbols_with_events,
        symbols_with_cycles=symbols_with_cycles,
        readiness_level="paper_live",
        health_trend="stable",
        persistence_status="healthy",
        nav_usd=10_000.0,
        last_error=None,
        ei_degraded=ei_degraded,
        ei_route_blocks=ei_route_blocks,
        ei_route_abstains=ei_route_abstains,
        recovery_incidents=recovery_incidents,
        stability=stability,
    )


def _make_acceptance(
    verdict: AcceptanceVerdict = AcceptanceVerdict.PASS,
) -> AcceptanceResult:
    return AcceptanceResult(
        verdict=verdict,
        criteria=(
            CriterionResult(
                name="min_events_processed",
                passed=True,
                severity="coverage",
                actual=1000,
                threshold=100,
                message="min_events_processed: 1000 ≥ 100",
            ),
        ),
        failed_criteria=(),
        warning_criteria=(),
        insufficient_criteria=(),
        summary="All criteria met.",
    )


def _make_participation(
    symbols: tuple[str, ...] = ("BTCUSDT", "ETHUSDT", "SOLUSDT"),
    exchange: str = "binance",
) -> tuple[SymbolParticipation, ...]:
    return tuple(
        SymbolParticipation(
            symbol=s,
            exchange=exchange,
            feed_ready=True,
            blocked=False,
            events_observed=True,
            cycles_observed=True,
        )
        for s in symbols
    )


def _make_report(
    *,
    campaign_id: str = "camp-1",
    status: str = "completed",
    verdict: AcceptanceVerdict = AcceptanceVerdict.PASS,
    total_cycles: int = 200,
    total_fills: int = 30,
    total_events: int = 1000,
    elapsed_seconds: float = 600.0,
    symbols: tuple[str, ...] = ("BTCUSDT", "ETHUSDT", "SOLUSDT"),
    exchange: str = "binance",
    ei_degraded: bool = False,
    ei_route_blocks: int = 0,
    ei_route_abstains: int = 0,
    recovery_incidents: int = 0,
    stability: StabilityRollup | None = None,
) -> CampaignReport:
    snap = _make_snapshot(
        campaign_id=campaign_id,
        total_cycles=total_cycles,
        total_fills=total_fills,
        total_events=total_events,
        elapsed_seconds=elapsed_seconds,
        symbol_count=len(symbols),
        symbols_with_events=len(symbols),
        symbols_with_cycles=len(symbols),
        ei_degraded=ei_degraded,
        ei_route_blocks=ei_route_blocks,
        ei_route_abstains=ei_route_abstains,
        recovery_incidents=recovery_incidents,
        stability=stability,
    )
    return CampaignReport(
        campaign_id=campaign_id,
        status=status,
        verdict=verdict.value,
        started_at_ns=_T0_NS,
        completed_at_ns=_T0_NS + int(elapsed_seconds * _NS_PER_S),
        elapsed_seconds=elapsed_seconds,
        run_id="run-1",
        snapshot=snap,
        acceptance=_make_acceptance(verdict),
        symbol_participation=_make_participation(symbols, exchange),
        config={},
        stability=stability,
    )


def _good_reports(n: int = 3) -> tuple[CampaignReport, ...]:
    """Create N good campaign reports that meet all promotion criteria."""
    return tuple(
        _make_report(
            campaign_id=f"camp-{i}",
            verdict=AcceptanceVerdict.PASS,
            total_cycles=200,
            total_fills=30,
            total_events=1000,
            elapsed_seconds=600.0,
            symbols=("BTCUSDT", "ETHUSDT", "SOLUSDT"),
        )
        for i in range(n)
    )


# ===========================================================================
# 1. Controller construction
# ===========================================================================


class TestControllerConstruction:
    def test_default_construction(self):
        ctrl = PromotionReviewController()
        assert ctrl.review_id.startswith("review-")
        assert ctrl.status == ReviewStatus.CREATED
        assert ctrl.campaign_count == 0
        assert ctrl.campaign_ids == ()
        assert ctrl.is_finalized is False

    def test_custom_review_id(self):
        ctrl = PromotionReviewController(
            review_id="rev-custom",
            readiness_level="paper_live",
            created_at_ns=_T0_NS,
        )
        assert ctrl.review_id == "rev-custom"
        assert ctrl.readiness_level == "paper_live"
        assert ctrl.readiness_is_supportive is True

    def test_initial_status_is_created(self):
        ctrl = PromotionReviewController()
        assert ctrl.status == ReviewStatus.CREATED
        assert ctrl.is_finalized is False
        assert ctrl.final_report is None


# ===========================================================================
# 2. Review status lifecycle transitions
# ===========================================================================


class TestReviewLifecycle:
    def test_created_to_collecting(self):
        ctrl = PromotionReviewController(created_at_ns=_T0_NS)
        assert ctrl.status == ReviewStatus.CREATED
        ctrl.add_campaign_report(_make_report(campaign_id="c1"))
        assert ctrl.status == ReviewStatus.COLLECTING

    def test_collecting_to_ready_to_evaluate(self):
        ctrl = PromotionReviewController(created_at_ns=_T0_NS)
        for i in range(3):
            ctrl.add_campaign_report(_make_report(campaign_id=f"c{i}"))
        assert ctrl.status == ReviewStatus.READY_TO_EVALUATE

    def test_ready_to_evaluate_to_finalized(self):
        ctrl = PromotionReviewController(review_id="rev-1", created_at_ns=_T0_NS)
        for r in _good_reports(3):
            ctrl.add_campaign_report(r)
        assert ctrl.status == ReviewStatus.READY_TO_EVALUATE
        ctrl.finalize_review(finalized_at_ns=_T0_NS)
        assert ctrl.status == ReviewStatus.FINALIZED
        assert ctrl.is_finalized is True

    def test_finalize_sets_rejected_on_reject_verdict(self):
        ctrl = PromotionReviewController(review_id="rev-rej", created_at_ns=_T0_NS)
        # Two failed + one pass → REJECT due to max_failed_campaigns
        ctrl.add_campaign_report(_make_report(campaign_id="c1", verdict=AcceptanceVerdict.FAIL))
        ctrl.add_campaign_report(_make_report(campaign_id="c2", verdict=AcceptanceVerdict.FAIL))
        ctrl.add_campaign_report(_make_report(campaign_id="c3", verdict=AcceptanceVerdict.PASS))
        final = ctrl.finalize_review(finalized_at_ns=_T0_NS)
        assert ctrl.status == ReviewStatus.REJECTED
        assert final.verdict == PromotionVerdict.REJECT.value

    def test_cannot_add_after_finalized(self):
        ctrl = PromotionReviewController(review_id="rev-1", created_at_ns=_T0_NS)
        for r in _good_reports(3):
            ctrl.add_campaign_report(r)
        ctrl.finalize_review(finalized_at_ns=_T0_NS)
        with pytest.raises(RuntimeError, match="terminal status"):
            ctrl.add_campaign_report(_make_report(campaign_id="c-extra"))

    def test_remove_reduces_status(self):
        ctrl = PromotionReviewController(created_at_ns=_T0_NS)
        for i in range(3):
            ctrl.add_campaign_report(_make_report(campaign_id=f"c{i}"))
        assert ctrl.status == ReviewStatus.READY_TO_EVALUATE
        ctrl.remove_campaign("c2")
        assert ctrl.status == ReviewStatus.COLLECTING
        assert ctrl.campaign_count == 2

    def test_reset_clears_state(self):
        ctrl = PromotionReviewController(created_at_ns=_T0_NS)
        for r in _good_reports(3):
            ctrl.add_campaign_report(r)
        ctrl.finalize_review(finalized_at_ns=_T0_NS)
        ctrl.reset()
        assert ctrl.status == ReviewStatus.CREATED
        assert ctrl.campaign_count == 0
        assert ctrl.final_report is None


# ===========================================================================
# 3. Campaign intake from completed reports
# ===========================================================================


class TestCampaignIntake:
    def test_add_completed_campaign(self):
        ctrl = PromotionReviewController(created_at_ns=_T0_NS)
        report = _make_report(campaign_id="c1", status="completed")
        ctrl.add_campaign_report(report)
        assert ctrl.campaign_count == 1
        assert "c1" in ctrl.campaign_ids

    def test_add_rejected_status_campaign(self):
        ctrl = PromotionReviewController(created_at_ns=_T0_NS)
        report = _make_report(
            campaign_id="c1",
            status="rejected",
            verdict=AcceptanceVerdict.FAIL,
        )
        ctrl.add_campaign_report(report)
        assert ctrl.campaign_count == 1

    def test_add_multiple_campaigns(self):
        ctrl = PromotionReviewController(created_at_ns=_T0_NS)
        for i in range(5):
            ctrl.add_campaign_report(_make_report(campaign_id=f"c{i}"))
        assert ctrl.campaign_count == 5
        assert ctrl.campaign_ids == ("c0", "c1", "c2", "c3", "c4")


# ===========================================================================
# 4. Duplicate campaign handling
# ===========================================================================


class TestDuplicateHandling:
    def test_duplicate_campaign_rejected(self):
        ctrl = PromotionReviewController(created_at_ns=_T0_NS)
        ctrl.add_campaign_report(_make_report(campaign_id="c1"))
        with pytest.raises(CampaignIntakeError, match="duplicates rejected"):
            ctrl.add_campaign_report(_make_report(campaign_id="c1"))
        assert ctrl.campaign_count == 1

    def test_same_set_same_result(self):
        """Same campaign set produces identical promotion results."""
        reports = _good_reports(3)

        ctrl_a = PromotionReviewController(review_id="rev-a", created_at_ns=_T0_NS)
        for r in reports:
            ctrl_a.add_campaign_report(r)
        final_a = ctrl_a.finalize_review(finalized_at_ns=_T0_NS)

        ctrl_b = PromotionReviewController(review_id="rev-b", created_at_ns=_T0_NS)
        for r in reports:
            ctrl_b.add_campaign_report(r)
        final_b = ctrl_b.finalize_review(finalized_at_ns=_T0_NS)

        assert final_a.verdict == final_b.verdict
        assert final_a.pass_criteria == final_b.pass_criteria
        assert final_a.fail_criteria == final_b.fail_criteria
        assert final_a.insufficient_evidence == final_b.insufficient_evidence
        assert final_a.campaign_count == final_b.campaign_count


# ===========================================================================
# 5. Malformed/non-completed campaign rejection
# ===========================================================================


class TestMalformedCampaignRejection:
    def test_running_status_rejected(self):
        ctrl = PromotionReviewController(created_at_ns=_T0_NS)
        report = _make_report(campaign_id="c1", status="running")
        with pytest.raises(CampaignIntakeError, match="ineligible status"):
            ctrl.add_campaign_report(report)

    def test_aborted_status_rejected(self):
        ctrl = PromotionReviewController(created_at_ns=_T0_NS)
        report = _make_report(campaign_id="c1", status="aborted")
        with pytest.raises(CampaignIntakeError, match="ineligible status"):
            ctrl.add_campaign_report(report)

    def test_failed_status_rejected(self):
        ctrl = PromotionReviewController(created_at_ns=_T0_NS)
        report = _make_report(campaign_id="c1", status="failed")
        with pytest.raises(CampaignIntakeError, match="ineligible status"):
            ctrl.add_campaign_report(report)

    def test_invalid_verdict_rejected(self):
        ctrl = PromotionReviewController(created_at_ns=_T0_NS)
        # Create a report with a non-standard verdict
        snap = _make_snapshot(campaign_id="c1")
        report = CampaignReport(
            campaign_id="c1",
            status="completed",
            verdict="unknown_verdict",
            started_at_ns=_T0_NS,
            completed_at_ns=_T0_NS + 600 * _NS_PER_S,
            elapsed_seconds=600.0,
            run_id="run-1",
            snapshot=snap,
            acceptance=_make_acceptance(),
            symbol_participation=_make_participation(),
            config={},
        )
        with pytest.raises(CampaignIntakeError, match="invalid verdict"):
            ctrl.add_campaign_report(report)

    def test_empty_campaign_id_rejected(self):
        ctrl = PromotionReviewController(created_at_ns=_T0_NS)
        snap = _make_snapshot(campaign_id="")
        report = CampaignReport(
            campaign_id="",
            status="completed",
            verdict="pass",
            started_at_ns=_T0_NS,
            completed_at_ns=_T0_NS + 600 * _NS_PER_S,
            elapsed_seconds=600.0,
            run_id="run-1",
            snapshot=snap,
            acceptance=_make_acceptance(),
            symbol_participation=_make_participation(),
            config={},
        )
        with pytest.raises(CampaignIntakeError, match="empty campaign_id"):
            ctrl.add_campaign_report(report)


# ===========================================================================
# 6. Provisional recommendation snapshot
# ===========================================================================


class TestProvisionalSnapshot:
    def test_empty_snapshot(self):
        ctrl = PromotionReviewController(review_id="rev-1", created_at_ns=_T0_NS)
        snap = ctrl.current_snapshot()
        assert isinstance(snap, CurrentReviewSnapshot)
        assert snap.review_id == "rev-1"
        assert snap.status == "created"
        assert snap.campaign_count == 0
        assert snap.provisional_verdict is None
        assert snap.is_ready_to_finalize is False

    def test_snapshot_with_campaigns(self):
        ctrl = PromotionReviewController(
            review_id="rev-1",
            readiness_level="paper_live",
            created_at_ns=_T0_NS,
        )
        for r in _good_reports(3):
            ctrl.add_campaign_report(r)
        snap = ctrl.current_snapshot()
        assert snap.campaign_count == 3
        assert snap.provisional_verdict is not None
        assert snap.is_ready_to_finalize is True
        assert snap.readiness_is_supportive is True
        assert len(snap.campaign_ids) == 3

    def test_snapshot_insufficient_campaigns(self):
        ctrl = PromotionReviewController(review_id="rev-1", created_at_ns=_T0_NS)
        ctrl.add_campaign_report(_make_report(campaign_id="c1"))
        snap = ctrl.current_snapshot()
        assert snap.campaign_count == 1
        assert snap.provisional_verdict == PromotionVerdict.INCONCLUSIVE.value
        assert len(snap.insufficient_evidence) > 0

    def test_snapshot_frozen(self):
        ctrl = PromotionReviewController(created_at_ns=_T0_NS)
        snap = ctrl.current_snapshot()
        with pytest.raises(AttributeError):
            snap.review_id = "x"  # type: ignore[misc]


# ===========================================================================
# 7. Final review report correctness
# ===========================================================================


class TestFinalReport:
    def test_final_report_correctness(self):
        ctrl = PromotionReviewController(
            review_id="rev-final",
            readiness_level="paper_live",
            created_at_ns=_T0_NS,
        )
        for r in _good_reports(3):
            ctrl.add_campaign_report(r)
        final = ctrl.finalize_review(finalized_at_ns=_T0_NS)

        assert isinstance(final, FinalReviewReport)
        assert final.review_id == "rev-final"
        assert final.finalized_at_ns == _T0_NS
        assert final.verdict == PromotionVerdict.PROMOTE.value
        assert final.campaign_count == 3
        assert len(final.campaign_ids) == 3
        assert len(final.fail_criteria) == 0
        assert len(final.insufficient_evidence) == 0
        assert final.readiness_level == "paper_live"
        assert final.readiness_is_supportive is True
        assert isinstance(final.execution_calibration_quality, dict)
        assert isinstance(final.coverage_stability_breadth, dict)
        assert isinstance(final.reason_codes, dict)
        assert final.summary != ""

    def test_final_report_with_failures(self):
        ctrl = PromotionReviewController(
            review_id="rev-fail",
            created_at_ns=_T0_NS,
        )
        ctrl.add_campaign_report(_make_report(campaign_id="c1", verdict=AcceptanceVerdict.FAIL))
        ctrl.add_campaign_report(_make_report(campaign_id="c2", verdict=AcceptanceVerdict.FAIL))
        ctrl.add_campaign_report(_make_report(campaign_id="c3", verdict=AcceptanceVerdict.PASS))
        final = ctrl.finalize_review(finalized_at_ns=_T0_NS)
        assert final.verdict == PromotionVerdict.REJECT.value
        assert len(final.fail_criteria) > 0

    def test_repeated_finalize_idempotent(self):
        ctrl = PromotionReviewController(review_id="rev-idem", created_at_ns=_T0_NS)
        for r in _good_reports(3):
            ctrl.add_campaign_report(r)
        final_1 = ctrl.finalize_review(finalized_at_ns=_T0_NS)
        final_2 = ctrl.finalize_review(finalized_at_ns=_T0_NS + 1000)
        assert final_1 is final_2  # same object, not re-computed

    def test_cannot_finalize_empty(self):
        ctrl = PromotionReviewController(created_at_ns=_T0_NS)
        with pytest.raises(RuntimeError, match="no campaigns"):
            ctrl.finalize_review()

    def test_final_report_frozen(self):
        ctrl = PromotionReviewController(review_id="rev-1", created_at_ns=_T0_NS)
        for r in _good_reports(3):
            ctrl.add_campaign_report(r)
        final = ctrl.finalize_review(finalized_at_ns=_T0_NS)
        with pytest.raises(AttributeError):
            final.verdict = "x"  # type: ignore[misc]


# ===========================================================================
# 8. Persistence write/read
# ===========================================================================


class TestPersistence:
    def test_save_workflow_state(self, tmp_path: Path):
        store = EvidenceStore(
            evidence_dir=tmp_path / "evidence",
            config=EvidenceStoreConfig(),
        )
        ctrl = PromotionReviewController(
            review_id="rev-persist",
            readiness_level="paper_live",
            evidence_store=store,
            created_at_ns=_T0_NS,
        )
        for r in _good_reports(3):
            ctrl.add_campaign_report(r)
        result = ctrl.save_state()
        assert result is not None
        assert result.success

    def test_save_and_restore_roundtrip(self, tmp_path: Path):
        store = EvidenceStore(
            evidence_dir=tmp_path / "evidence",
            config=EvidenceStoreConfig(),
        )
        reports = _good_reports(3)
        reports_by_id = {r.campaign_id: r for r in reports}

        ctrl = PromotionReviewController(
            review_id="rev-rt",
            readiness_level="paper_live",
            evidence_store=store,
            created_at_ns=_T0_NS,
        )
        for r in reports:
            ctrl.add_campaign_report(r)
        ctrl.save_state()

        restored = PromotionReviewController.restore(store, reports_by_id)
        assert restored.review_id == "rev-rt"
        assert restored.campaign_count == 3
        assert restored.campaign_ids == ctrl.campaign_ids
        assert restored.readiness_level == "paper_live"

    def test_finalize_persists_final_review(self, tmp_path: Path):
        store = EvidenceStore(
            evidence_dir=tmp_path / "evidence",
            config=EvidenceStoreConfig(),
        )
        ctrl = PromotionReviewController(
            review_id="rev-fp",
            readiness_level="paper_live",
            evidence_store=store,
            created_at_ns=_T0_NS,
        )
        for r in _good_reports(3):
            ctrl.add_campaign_report(r)
        ctrl.finalize_review(finalized_at_ns=_T0_NS)

        # Verify final review was persisted via PromotionReviewStore
        from crypto_core.service.promotion_review import (
            PromotionReviewStore,
        )

        review_store = PromotionReviewStore(store)
        loaded = review_store.load_review()
        assert loaded["review_id"] == "rev-fp"
        assert loaded["verdict"] == "promote"


# ===========================================================================
# 9. Malformed restore fail-closed
# ===========================================================================


class TestMalformedRestore:
    def test_non_dict_data_fail_closed(self, tmp_path: Path):
        store = EvidenceStore(
            evidence_dir=tmp_path / "evidence",
            config=EvidenceStoreConfig(),
        )
        store.save_snapshot("promotion_review_workflow", "not-a-dict")
        with pytest.raises(ReviewWorkflowCorruptError, match="must be a dict"):
            PromotionReviewController.restore(store, {})

    def test_missing_fields_fail_closed(self, tmp_path: Path):
        store = EvidenceStore(
            evidence_dir=tmp_path / "evidence",
            config=EvidenceStoreConfig(),
        )
        store.save_snapshot("promotion_review_workflow", {"review_id": "x"})
        with pytest.raises(ReviewWorkflowCorruptError, match="missing required fields"):
            PromotionReviewController.restore(store, {})

    def test_invalid_status_fail_closed(self, tmp_path: Path):
        store = EvidenceStore(
            evidence_dir=tmp_path / "evidence",
            config=EvidenceStoreConfig(),
        )
        store.save_snapshot(
            "promotion_review_workflow",
            {
                "review_id": "x",
                "status": "INVALID_STATUS",
                "created_at_ns": _T0_NS,
                "campaign_ids": [],
            },
        )
        with pytest.raises(ReviewWorkflowCorruptError, match="Invalid review status"):
            PromotionReviewController.restore(store, {})

    def test_missing_campaign_report_fail_closed(self, tmp_path: Path):
        store = EvidenceStore(
            evidence_dir=tmp_path / "evidence",
            config=EvidenceStoreConfig(),
        )
        store.save_snapshot(
            "promotion_review_workflow",
            {
                "review_id": "x",
                "status": "collecting",
                "created_at_ns": _T0_NS,
                "campaign_ids": ["c1", "c2"],
            },
        )
        # Only provide c1, not c2
        reports_by_id = {"c1": _make_report(campaign_id="c1")}
        with pytest.raises(ReviewWorkflowCorruptError, match="Missing campaign reports"):
            PromotionReviewController.restore(store, reports_by_id)


# ===========================================================================
# 10. Deterministic replay / restore
# ===========================================================================


class TestDeterministicReplay:
    def test_same_input_same_output(self):
        """Same campaign set → same verdict, same criteria, same report."""
        reports = _good_reports(3)

        ctrl_a = PromotionReviewController(review_id="rev-a", created_at_ns=_T0_NS)
        for r in reports:
            ctrl_a.add_campaign_report(r)
        result_a = ctrl_a.evaluate()

        ctrl_b = PromotionReviewController(review_id="rev-b", created_at_ns=_T0_NS)
        for r in reports:
            ctrl_b.add_campaign_report(r)
        result_b = ctrl_b.evaluate()

        assert result_a.verdict == result_b.verdict
        assert len(result_a.criteria) == len(result_b.criteria)
        for ca, cb in zip(result_a.criteria, result_b.criteria):
            assert ca.name == cb.name
            assert ca.passed == cb.passed
            assert ca.actual == cb.actual

    def test_restore_produces_same_result(self, tmp_path: Path):
        store = EvidenceStore(
            evidence_dir=tmp_path / "evidence",
            config=EvidenceStoreConfig(),
        )
        reports = _good_reports(3)
        reports_by_id = {r.campaign_id: r for r in reports}

        ctrl = PromotionReviewController(
            review_id="rev-det",
            readiness_level="paper_live",
            evidence_store=store,
            created_at_ns=_T0_NS,
        )
        for r in reports:
            ctrl.add_campaign_report(r)
        original_result = ctrl.evaluate()
        ctrl.save_state()

        restored = PromotionReviewController.restore(store, reports_by_id)
        restored_result = restored.evaluate()

        assert original_result.verdict == restored_result.verdict
        assert len(original_result.criteria) == len(restored_result.criteria)


# ===========================================================================
# 11. Readiness interaction truthfulness
# ===========================================================================


class TestReadinessInteraction:
    def test_not_assessed_not_supportive(self):
        ctrl = PromotionReviewController(readiness_level="not_assessed", created_at_ns=_T0_NS)
        assert ctrl.readiness_is_supportive is False
        for r in _good_reports(3):
            ctrl.add_campaign_report(r)
        final = ctrl.finalize_review(finalized_at_ns=_T0_NS)
        assert final.readiness_is_supportive is False

    def test_paper_live_is_supportive(self):
        ctrl = PromotionReviewController(readiness_level="paper_live", created_at_ns=_T0_NS)
        assert ctrl.readiness_is_supportive is True
        for r in _good_reports(3):
            ctrl.add_campaign_report(r)
        final = ctrl.finalize_review(finalized_at_ns=_T0_NS)
        assert final.readiness_is_supportive is True

    def test_readiness_does_not_auto_finalize(self):
        """Good readiness alone does not finalize or promote review."""
        ctrl = PromotionReviewController(readiness_level="shadow_live", created_at_ns=_T0_NS)
        assert ctrl.readiness_is_supportive is True
        assert ctrl.status == ReviewStatus.CREATED
        assert ctrl.is_finalized is False

    def test_good_readiness_insufficient_campaigns_inconclusive(self):
        """Readiness is supportive but single campaign → INCONCLUSIVE."""
        ctrl = PromotionReviewController(readiness_level="calibrated_paper", created_at_ns=_T0_NS)
        ctrl.add_campaign_report(_make_report(campaign_id="c1"))
        snap = ctrl.current_snapshot()
        assert snap.readiness_is_supportive is True
        assert snap.provisional_verdict == PromotionVerdict.INCONCLUSIVE.value

    def test_mixed_campaigns_despite_good_readiness(self):
        """Good readiness but mixed campaign results → REJECT."""
        ctrl = PromotionReviewController(readiness_level="shadow_live", created_at_ns=_T0_NS)
        ctrl.add_campaign_report(_make_report(campaign_id="c1", verdict=AcceptanceVerdict.FAIL))
        ctrl.add_campaign_report(_make_report(campaign_id="c2", verdict=AcceptanceVerdict.FAIL))
        ctrl.add_campaign_report(_make_report(campaign_id="c3", verdict=AcceptanceVerdict.PASS))
        final = ctrl.finalize_review(finalized_at_ns=_T0_NS)
        assert final.readiness_is_supportive is True
        assert final.verdict == PromotionVerdict.REJECT.value


# ===========================================================================
# 12. Reporting API views
# ===========================================================================


class TestReportingAPI:
    def test_verdict_distribution_empty(self):
        ctrl = PromotionReviewController(created_at_ns=_T0_NS)
        dist = ctrl.get_verdict_distribution()
        assert dist["total"] == 0

    def test_verdict_distribution_with_campaigns(self):
        ctrl = PromotionReviewController(created_at_ns=_T0_NS)
        ctrl.add_campaign_report(_make_report(campaign_id="c1", verdict=AcceptanceVerdict.PASS))
        ctrl.add_campaign_report(_make_report(campaign_id="c2", verdict=AcceptanceVerdict.FAIL))
        dist = ctrl.get_verdict_distribution()
        assert dist["total"] == 2
        assert dist["passed"] == 1
        assert dist["failed"] == 1

    def test_execution_sufficiency(self):
        ctrl = PromotionReviewController(created_at_ns=_T0_NS)
        for r in _good_reports(3):
            ctrl.add_campaign_report(r)
        suf = ctrl.get_execution_sufficiency()
        assert suf["total_campaigns"] == 3
        assert "sufficiency_distribution" in suf

    def test_missing_evidence_empty(self):
        ctrl = PromotionReviewController(created_at_ns=_T0_NS)
        missing = ctrl.get_missing_evidence()
        assert missing["campaign_count"] == 0

    def test_missing_evidence_with_campaigns(self):
        ctrl = PromotionReviewController(created_at_ns=_T0_NS)
        ctrl.add_campaign_report(_make_report(campaign_id="c1"))
        missing = ctrl.get_missing_evidence()
        assert missing["campaign_count"] == 1
        assert missing["provisional_verdict"] is not None

    def test_provisional_recommendation_empty(self):
        ctrl = PromotionReviewController(created_at_ns=_T0_NS)
        rec = ctrl.get_provisional_recommendation()
        assert rec["verdict"] is None

    def test_provisional_recommendation_with_campaigns(self):
        ctrl = PromotionReviewController(readiness_level="paper_live", created_at_ns=_T0_NS)
        for r in _good_reports(3):
            ctrl.add_campaign_report(r)
        rec = ctrl.get_provisional_recommendation()
        assert rec["verdict"] == PromotionVerdict.PROMOTE.value
        assert rec["readiness_is_supportive"] is True

    def test_promotion_reason_summary_empty(self):
        ctrl = PromotionReviewController(created_at_ns=_T0_NS)
        prs = ctrl.get_promotion_reason_summary()
        assert prs["verdict"] is None

    def test_promotion_reason_summary_with_campaigns(self):
        ctrl = PromotionReviewController(created_at_ns=_T0_NS)
        for r in _good_reports(3):
            ctrl.add_campaign_report(r)
        prs = ctrl.get_promotion_reason_summary()
        assert prs["verdict"] == PromotionVerdict.PROMOTE.value
        assert isinstance(prs["pass_reasons"], list)


# ===========================================================================
# 13. Symbol breadth and distribution summaries
# ===========================================================================


class TestSymbolBreadthDistribution:
    def test_multi_exchange_symbols(self):
        ctrl = PromotionReviewController(created_at_ns=_T0_NS)
        ctrl.add_campaign_report(
            _make_report(
                campaign_id="c1",
                symbols=("BTCUSDT", "ETHUSDT"),
                exchange="binance",
            )
        )
        ctrl.add_campaign_report(
            _make_report(
                campaign_id="c2",
                symbols=("ETHUSDT", "SOLUSDT"),
                exchange="bybit",
            )
        )
        ctrl.add_campaign_report(
            _make_report(
                campaign_id="c3",
                symbols=("BTCUSDT", "SOLUSDT"),
                exchange="binance",
            )
        )
        breadth = ctrl.get_symbol_breadth()
        assert set(breadth["unique_symbols"]) == {
            "BTCUSDT",
            "ETHUSDT",
            "SOLUSDT",
        }
        assert set(breadth["unique_exchanges"]) == {"binance", "bybit"}
        assert breadth["total_campaigns"] == 3

    def test_empty_review_returns_empty(self):
        ctrl = PromotionReviewController(created_at_ns=_T0_NS)
        breadth = ctrl.get_symbol_breadth()
        assert breadth["unique_symbols"] == []
        assert breadth["total_campaigns"] == 0


# ===========================================================================
# 14. Serialization helpers
# ===========================================================================


class TestSerialization:
    def test_current_review_snapshot_to_dict(self):
        ctrl = PromotionReviewController(
            review_id="rev-ser",
            readiness_level="paper_live",
            created_at_ns=_T0_NS,
        )
        for r in _good_reports(3):
            ctrl.add_campaign_report(r)
        snap = ctrl.current_snapshot()
        d = current_review_snapshot_to_dict(snap)
        assert d["review_id"] == "rev-ser"
        assert d["campaign_count"] == 3
        assert d["readiness_is_supportive"] is True
        assert isinstance(d["verdict_distribution"], dict)

    def test_final_review_report_to_dict(self):
        ctrl = PromotionReviewController(
            review_id="rev-ser2",
            readiness_level="paper_live",
            created_at_ns=_T0_NS,
        )
        for r in _good_reports(3):
            ctrl.add_campaign_report(r)
        final = ctrl.finalize_review(finalized_at_ns=_T0_NS)
        d = final_review_report_to_dict(final)
        assert d["review_id"] == "rev-ser2"
        assert d["verdict"] == "promote"
        assert d["campaign_count"] == 3
        assert isinstance(d["pass_criteria"], list)
        assert isinstance(d["reason_codes"], dict)
