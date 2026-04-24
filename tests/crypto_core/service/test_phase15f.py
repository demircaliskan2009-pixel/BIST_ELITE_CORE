"""Tests for Phase 15F - Crypto sleeve admission gate."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from crypto_core.service.models import QueuePressure, QueueSnapshot, ServiceStatus, WatchdogStatus
from crypto_core.service.service_orchestrator import ServiceOrchestrator, operator_snapshot_to_dict
from crypto_core.service.sleeve_admission_controller import (
    SleeveAdmissionController,
    SleeveAdmissionCorruptError,
    SleeveAdmissionVerdict,
    sleeve_admission_snapshot_from_dict,
    sleeve_admission_snapshot_to_dict,
)
from crypto_core.service.sleeve_candidate_workflow import (
    SleeveCandidateWorkflowEntry,
    SleeveCandidateWorkflowSnapshot,
)
from crypto_core.service.sleeve_portfolio import (
    CryptoSleeveState,
    CryptoSleeveStatus,
    CryptoSleeveType,
    SleeveCampaignEvidenceResult,
    SleeveCampaignEvidenceStatus,
    SleeveDecisionPackResult,
    SleeveDecisionPackStatus,
    SleeveEvidenceState,
    SleevePortfolioSnapshot,
    SleevePromotionCandidateResult,
    SleevePromotionCandidateStatus,
    SleevePromotionSupportResult,
    SleevePromotionSupportStatus,
    SleeveQualificationResult,
    SleeveQualificationStatus,
    SleeveRecommendationResult,
    SleeveRecommendationStatus,
)
from crypto_core.service.sleeve_promotion_review_controller import (
    SleevePromotionReviewPortfolioSummary,
    SleevePromotionReviewResult,
    SleevePromotionReviewVerdict,
)

_T0_NS = 1_000_000_000_000


def _review_result(
    sleeve_id: str,
    verdict: SleevePromotionReviewVerdict = SleevePromotionReviewVerdict.REVIEW_SUPPORTED,
    *,
    governance_blockers: tuple[str, ...] = (),
    missing_evidence: tuple[str, ...] = (),
    next_step: str = "continue_paper_review",
) -> SleevePromotionReviewResult:
    return SleevePromotionReviewResult(
        sleeve_id=sleeve_id,
        verdict=verdict,
        reason="review reason",
        next_step=next_step,
        missing_evidence=missing_evidence,
        governance_blockers=governance_blockers,
    )


def _review_summary(*results: SleevePromotionReviewResult) -> SleevePromotionReviewPortfolioSummary:
    return SleevePromotionReviewPortfolioSummary(
        as_of_ns=_T0_NS,
        review_results=tuple(results),
        supported=tuple(r.sleeve_id for r in results if r.verdict == SleevePromotionReviewVerdict.REVIEW_SUPPORTED),
        hold=tuple(r.sleeve_id for r in results if r.verdict == SleevePromotionReviewVerdict.HOLD),
        reject=tuple(r.sleeve_id for r in results if r.verdict == SleevePromotionReviewVerdict.REJECT),
        inconclusive=tuple(r.sleeve_id for r in results if r.verdict == SleevePromotionReviewVerdict.INCONCLUSIVE),
        repeated_weak=(),
        repeated_blocked=(),
        repeated_inconclusive=(),
        missing_evidence=tuple(dict.fromkeys(code for r in results for code in r.missing_evidence)),
        governance_blockers=tuple(dict.fromkeys(code for r in results for code in r.governance_blockers)),
        operator_summary="review summary",
    )


def _sleeve(
    sleeve_id: str,
    *,
    status: CryptoSleeveStatus = CryptoSleeveStatus.ALLOCATED,
    recommendation_status: SleeveRecommendationStatus = SleeveRecommendationStatus.RECOMMENDED_ACTIVE,
    qualification_status: SleeveQualificationStatus = SleeveQualificationStatus.PAPER_QUALIFIED,
    campaign_status: SleeveCampaignEvidenceStatus = SleeveCampaignEvidenceStatus.CAMPAIGN_SUPPORTED,
    support_status: SleevePromotionSupportStatus = SleevePromotionSupportStatus.SUPPORTIVE,
    candidate_status: SleevePromotionCandidateStatus = SleevePromotionCandidateStatus.SUPPORTED,
    decision_status: SleeveDecisionPackStatus = SleeveDecisionPackStatus.RECOMMENDED_ACTIVE,
    effective_allocation: float = 0.25,
    target_allocation: float = 0.25,
    missing_evidence: tuple[str, ...] = (),
    blockers: tuple[str, ...] = (),
) -> CryptoSleeveState:
    return CryptoSleeveState(
        sleeve_id=sleeve_id,
        sleeve_type=CryptoSleeveType.MICROSTRUCTURE,
        status=status,
        target_allocation=target_allocation,
        active_allocation=effective_allocation,
        effective_allocation=effective_allocation,
        blocked_reasons=blockers,
        qualification=SleeveQualificationResult(
            status=qualification_status,
            qualified_for_paper_allocation=qualification_status == SleeveQualificationStatus.PAPER_QUALIFIED,
            governance_blocked=bool(blockers),
            missing_evidence=missing_evidence,
            blocking_reasons=blockers,
            evidence=SleeveEvidenceState(supportive=not blockers and not missing_evidence),
            reason_summary="qualification reason",
            next_step="qualification next",
        ),
        recommendation=SleeveRecommendationResult(
            status=recommendation_status,
            recommended_active=recommendation_status == SleeveRecommendationStatus.RECOMMENDED_ACTIVE,
            currently_eligible=recommendation_status
            in {
                SleeveRecommendationStatus.RECOMMENDED_ACTIVE,
                SleeveRecommendationStatus.ELIGIBLE_BUT_NOT_SELECTED,
            },
            qualification_status=qualification_status,
            effective_allocation=effective_allocation,
            target_allocation=target_allocation,
            missing_evidence=missing_evidence,
            blocking_reasons=blockers,
            reason_summary="recommendation reason",
            next_step="recommendation next",
        ),
        campaign_evidence=SleeveCampaignEvidenceResult(
            status=campaign_status,
            campaign_evidence_available=campaign_status == SleeveCampaignEvidenceStatus.CAMPAIGN_SUPPORTED,
            explicit_link_available=campaign_status == SleeveCampaignEvidenceStatus.CAMPAIGN_SUPPORTED,
            linked_in_campaign=campaign_status == SleeveCampaignEvidenceStatus.CAMPAIGN_SUPPORTED,
            missing_evidence=missing_evidence,
            blocking_reasons=blockers,
            reason_summary="campaign reason",
            next_step="campaign next",
        ),
        promotion_support=SleevePromotionSupportResult(
            status=support_status,
            can_be_considered_later=support_status
            in {SleevePromotionSupportStatus.SUPPORTIVE, SleevePromotionSupportStatus.WEAK_SUPPORT},
            campaign_evidence_status=campaign_status,
            qualification_status=qualification_status,
            recommendation_status=recommendation_status,
            missing_evidence=missing_evidence,
            blocking_reasons=blockers,
            reason_summary="support reason",
            next_step="support next",
        ),
        promotion_candidate=SleevePromotionCandidateResult(
            status=candidate_status,
            candidate_for_future_review=candidate_status
            in {SleevePromotionCandidateStatus.SUPPORTED, SleevePromotionCandidateStatus.WATCHLIST},
            strongly_supported=candidate_status == SleevePromotionCandidateStatus.SUPPORTED,
            campaign_evidence_status=campaign_status,
            promotion_support_status=support_status,
            qualification_status=qualification_status,
            recommendation_status=recommendation_status,
            missing_evidence=missing_evidence,
            blocking_reasons=blockers,
            reason_summary="candidate reason",
            next_step="candidate next",
        ),
        decision_pack=SleeveDecisionPackResult(
            status=decision_status,
            recommended_active=decision_status == SleeveDecisionPackStatus.RECOMMENDED_ACTIVE,
            currently_eligible=decision_status
            in {
                SleeveDecisionPackStatus.RECOMMENDED_ACTIVE,
                SleeveDecisionPackStatus.ELIGIBLE_BUT_NOT_SELECTED,
            },
            promotion_candidate=candidate_status
            in {SleevePromotionCandidateStatus.SUPPORTED, SleevePromotionCandidateStatus.WATCHLIST},
            strongly_supported_candidate=candidate_status == SleevePromotionCandidateStatus.SUPPORTED,
            recommendation_status=recommendation_status,
            qualification_status=qualification_status,
            campaign_evidence_status=campaign_status,
            promotion_support_status=support_status,
            promotion_candidate_status=candidate_status,
            missing_evidence=missing_evidence,
            blocking_reasons=blockers,
            reason_summary="decision reason",
            next_step="decision next",
        ),
    )


def _portfolio(*sleeves: CryptoSleeveState) -> SleevePortfolioSnapshot:
    return SleevePortfolioSnapshot(as_of_ns=_T0_NS, sleeves=tuple(sleeves))


def _mock_service() -> MagicMock:
    queue = QueueSnapshot(
        current_depth=0,
        max_size=100,
        pressure=QueuePressure.NORMAL,
        total_enqueued=0,
        total_dropped=0,
        total_processed=0,
    )
    watchdog = WatchdogStatus(
        consumer_alive=True,
        last_event_time_ns=_T0_NS,
        last_cycle_time_ns=_T0_NS,
        seconds_since_event=0.0,
        seconds_since_cycle=0.0,
        stall_detected=False,
        stall_threshold_s=60.0,
    )
    status = ServiceStatus(
        service_mode="running",
        runtime_status=None,
        queue=queue,
        watchdog=watchdog,
        symbol_health=(),
        symbol_count=0,
        trading_enabled=True,
        blocked_reason=None,
        last_error=None,
    )
    service = MagicMock()
    service.status.return_value = status
    return service


def _supported_workflow(sleeve_id: str) -> SleeveCandidateWorkflowSnapshot:
    return SleeveCandidateWorkflowSnapshot(
        workflow_id="wf-admission",
        status="active",
        as_of_ns=_T0_NS,
        sleeves=(
            SleeveCandidateWorkflowEntry(
                sleeve_id=sleeve_id,
                candidate_status=SleevePromotionCandidateStatus.SUPPORTED,
                promotion_support_status=SleevePromotionSupportStatus.SUPPORTIVE,
                decision_pack_status=SleeveDecisionPackStatus.SUPPORTED_CANDIDATE,
                candidate_for_future_review=True,
                strongly_supported=True,
                reason_summary="supported",
                next_step="review",
            ),
        ),
    )


def test_admission_model_construction() -> None:
    controller = SleeveAdmissionController(
        _review_summary(_review_result("s1")),
        portfolio_snapshot=_portfolio(_sleeve("s1")),
    )

    result = controller.build_admission_results()[0]

    assert result.sleeve_id == "s1"
    assert result.verdict == SleeveAdmissionVerdict.ADMITTED_ACTIVE
    assert result.admitted is True
    assert result.active is True


def test_no_review_conservative_behavior() -> None:
    controller = SleeveAdmissionController(portfolio_snapshot=_portfolio(_sleeve("s1")))

    result = controller.build_admission_results()[0]

    assert result.verdict == SleeveAdmissionVerdict.INSUFFICIENT_EVIDENCE
    assert result.admitted is False
    assert result.evidence_blockers == ("promotion_review_unavailable",)


def test_admitted_active_sleeve() -> None:
    result = SleeveAdmissionController(
        _review_summary(_review_result("active")),
        portfolio_snapshot=_portfolio(_sleeve("active", effective_allocation=0.35)),
    ).build_admission_results()[0]

    assert result.verdict == SleeveAdmissionVerdict.ADMITTED_ACTIVE
    assert result.effective_allocation == pytest.approx(0.35)


def test_admitted_unallocated_sleeve() -> None:
    result = SleeveAdmissionController(
        _review_summary(_review_result("idle")),
        portfolio_snapshot=_portfolio(
            _sleeve(
                "idle",
                status=CryptoSleeveStatus.ENABLED,
                recommendation_status=SleeveRecommendationStatus.ELIGIBLE_BUT_NOT_SELECTED,
                decision_status=SleeveDecisionPackStatus.ELIGIBLE_BUT_NOT_SELECTED,
                effective_allocation=0.0,
            )
        ),
    ).build_admission_results()[0]

    assert result.verdict == SleeveAdmissionVerdict.ADMITTED_UNALLOCATED
    assert result.admitted is True
    assert result.active is False


def test_review_supported_not_admitted_sleeve() -> None:
    result = SleeveAdmissionController(_review_summary(_review_result("missing"))).build_admission_results()[0]

    assert result.verdict == SleeveAdmissionVerdict.REVIEW_SUPPORTED_NOT_ADMITTED
    assert result.evidence_blockers == ("sleeve_portfolio_unavailable",)


def test_blocked_sleeve() -> None:
    result = SleeveAdmissionController(
        _review_summary(_review_result("blocked", SleevePromotionReviewVerdict.REJECT)),
        portfolio_snapshot=_portfolio(
            _sleeve(
                "blocked",
                status=CryptoSleeveStatus.BLOCKED,
                recommendation_status=SleeveRecommendationStatus.BLOCKED,
                qualification_status=SleeveQualificationStatus.BLOCKED,
                campaign_status=SleeveCampaignEvidenceStatus.BLOCKED_BY_GOVERNANCE,
                support_status=SleevePromotionSupportStatus.BLOCKED,
                candidate_status=SleevePromotionCandidateStatus.BLOCKED,
                decision_status=SleeveDecisionPackStatus.BLOCKED,
                blockers=("readiness_pending",),
            )
        ),
    ).build_admission_results()[0]

    assert result.verdict == SleeveAdmissionVerdict.BLOCKED
    assert result.governance_blockers == ("readiness_pending",)


def test_inconclusive_sleeve() -> None:
    result = SleeveAdmissionController(
        _review_summary(_review_result("watch", SleevePromotionReviewVerdict.HOLD)),
        portfolio_snapshot=_portfolio(
            _sleeve(
                "watch",
                recommendation_status=SleeveRecommendationStatus.ELIGIBLE_BUT_NOT_SELECTED,
                support_status=SleevePromotionSupportStatus.WEAK_SUPPORT,
                candidate_status=SleevePromotionCandidateStatus.WATCHLIST,
                decision_status=SleeveDecisionPackStatus.WATCHLIST_CANDIDATE,
                effective_allocation=0.0,
            )
        ),
    ).build_admission_results()[0]

    assert result.verdict == SleeveAdmissionVerdict.INCONCLUSIVE


def test_disabled_operator_off_sleeve() -> None:
    result = SleeveAdmissionController(
        _review_summary(_review_result("disabled")),
        portfolio_snapshot=_portfolio(
            _sleeve(
                "disabled",
                status=CryptoSleeveStatus.DISABLED,
                recommendation_status=SleeveRecommendationStatus.DISABLED_OPERATOR_OFF,
                decision_status=SleeveDecisionPackStatus.BLOCKED,
                effective_allocation=0.0,
            )
        ),
    ).build_admission_results()[0]

    assert result.verdict == SleeveAdmissionVerdict.DISABLED_OPERATOR_OFF
    assert "disabled_operator_off" in result.governance_blockers


def test_portfolio_admission_summary() -> None:
    controller = SleeveAdmissionController(
        _review_summary(
            _review_result("active"),
            _review_result("idle"),
            _review_result("missing"),
            _review_result("blocked", SleevePromotionReviewVerdict.REJECT),
            _review_result("watch", SleevePromotionReviewVerdict.INCONCLUSIVE),
        ),
        portfolio_snapshot=_portfolio(
            _sleeve("active"),
            _sleeve(
                "idle",
                status=CryptoSleeveStatus.ENABLED,
                recommendation_status=SleeveRecommendationStatus.ELIGIBLE_BUT_NOT_SELECTED,
                effective_allocation=0.0,
            ),
            _sleeve("blocked", status=CryptoSleeveStatus.BLOCKED, blockers=("gov",)),
            _sleeve("watch", effective_allocation=0.0),
        ),
    )

    summary = controller.build_portfolio_summary()

    assert summary.admitted_active_count == 1
    assert summary.admitted_unallocated_count == 1
    assert summary.review_supported_not_admitted_count == 1
    assert summary.blocked_count == 1
    assert summary.inconclusive_count == 1
    assert "gov" in summary.governance_blockers
    assert "admitted_active=1" in summary.operator_summary


def test_reason_codes_and_next_step_summary() -> None:
    controller = SleeveAdmissionController(
        _review_summary(_review_result("s1", missing_evidence=("campaign_missing",))),
        portfolio_snapshot=_portfolio(_sleeve("s1")),
    )

    summary = controller.build_portfolio_summary()

    assert summary.evidence_blockers == ("campaign_missing",)
    assert "continue_paper_review" in summary.next_step_summary
    assert summary.review_supported_not_admitted == ("s1",)


def test_serialization_roundtrip() -> None:
    controller = SleeveAdmissionController(
        _review_summary(_review_result("s1")),
        portfolio_snapshot=_portfolio(_sleeve("s1")),
    )
    snapshot = controller.finalize()

    restored = sleeve_admission_snapshot_from_dict(sleeve_admission_snapshot_to_dict(snapshot))

    assert restored == snapshot


def test_restore_fail_closed_on_malformed_payload() -> None:
    payload = {
        "as_of_ns": _T0_NS,
        "status": "active",
        "admission_results": [],
        "portfolio_summary": {
            "as_of_ns": _T0_NS,
            "admission_results": [],
            "admitted_active_count": 1,
            "admitted_active": [],
            "admitted_unallocated": [],
            "review_supported_not_admitted": [],
            "blocked": [],
            "inconclusive": [],
            "governance_blockers": [],
            "evidence_blockers": [],
            "next_step_summary": "bad",
            "operator_summary": "bad",
        },
        "history": [],
    }

    with pytest.raises(SleeveAdmissionCorruptError):
        sleeve_admission_snapshot_from_dict(payload)


def test_service_orchestrator_integration() -> None:
    fixed_review_ns = _T0_NS + 42
    orch = ServiceOrchestrator(service=_mock_service(), sleeve_workflow_clock_ns=lambda: fixed_review_ns)
    orch.start_sleeve_promotion_review(workflow_snapshot=_supported_workflow("svc-sleeve"))

    snapshot = orch.get_sleeve_admission_snapshot(
        portfolio_snapshot=_portfolio(_sleeve("svc-sleeve", effective_allocation=0.20))
    )
    rendered = sleeve_admission_snapshot_to_dict(snapshot)

    assert snapshot.as_of_ns == fixed_review_ns
    assert snapshot.portfolio_summary.admitted_active == ("svc-sleeve",)
    assert rendered["portfolio_summary"]["admitted_active_count"] == 1


def test_operator_snapshot_surfaces_no_review_conservatively() -> None:
    orch = ServiceOrchestrator(service=_mock_service(), sleeves=(_sleeve("configured"),))

    snapshot = orch.operator_snapshot()
    rendered = operator_snapshot_to_dict(snapshot)

    assert snapshot.sleeve_admission is not None
    assert snapshot.sleeve_admission.portfolio_summary.insufficient_evidence_count == 1
    assert "promotion_review_unavailable" in rendered["sleeve_admission"]["portfolio_summary"]["evidence_blockers"]


def test_deterministic_replay() -> None:
    summary = _review_summary(_review_result("s1"))
    portfolio = _portfolio(_sleeve("s1"))

    first = sleeve_admission_snapshot_to_dict(
        SleeveAdmissionController(summary, portfolio_snapshot=portfolio).snapshot()
    )
    second = sleeve_admission_snapshot_to_dict(
        SleeveAdmissionController(summary, portfolio_snapshot=portfolio).snapshot()
    )

    assert first == second


def test_backward_compatibility_with_older_snapshot_state() -> None:
    old_result = {
        "sleeve_id": "old-blocked",
        "verdict": "not_admitted_blocked",
        "reason": "old reason",
        "next_step": "old next",
    }
    payload = {
        "as_of_ns": _T0_NS,
        "status": "active",
        "admission_results": [old_result],
        "portfolio_summary": {
            "as_of_ns": _T0_NS,
            "admission_results": [old_result],
            "admitted_active": [],
            "admitted_unallocated": [],
            "review_supported_not_admitted": [],
            "blocked": ["old-blocked"],
            "inconclusive": [],
            "governance_blockers": [],
            "evidence_blockers": [],
            "operator_summary": "old summary",
        },
        "history": [],
    }

    restored = sleeve_admission_snapshot_from_dict(payload)

    assert restored.portfolio_summary.blocked_count == 1
    assert restored.admission_results[0].verdict == SleeveAdmissionVerdict.NOT_ADMITTED_BLOCKED
