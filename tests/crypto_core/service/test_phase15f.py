"""Tests for Phase 15F - Crypto sleeve admission gate."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from crypto_core.service.artifact_export import (
    export_managed_sleeve_set_manifest,
    export_paper_shadow_activation_plan,
    export_sleeve_admission_release_pack,
    load_managed_sleeve_set_manifest,
    load_paper_shadow_activation_plan,
    load_sleeve_admission_release_pack,
)
from crypto_core.service.campaign import (
    AcceptanceResult,
    AcceptanceVerdict,
    CampaignReport,
    CampaignSleeveLinkSummary,
    CampaignSnapshot,
    CriterionResult,
)
from crypto_core.service.campaign_controller import campaign_readiness_flags
from crypto_core.service.evidence_store import EvidenceStore, EvidenceStoreConfig
from crypto_core.service.models import QueuePressure, QueueSnapshot, ServiceStatus, WatchdogStatus
from crypto_core.service.service_orchestrator import ServiceOrchestrator, operator_snapshot_to_dict
from crypto_core.service.sleeve_admission_controller import (
    ManagedSleeveSetDryRunStatus,
    PaperShadowActivationStatus,
    SleeveAdmissionController,
    SleeveAdmissionCorruptError,
    SleeveAdmissionReleaseEvidenceStatus,
    SleeveAdmissionReleaseStatus,
    SleeveAdmissionVerdict,
    build_managed_sleeve_set_manifest,
    build_paper_shadow_activation_plan,
    build_sleeve_admission_release_pack,
    managed_sleeve_set_manifest_from_dict,
    managed_sleeve_set_manifest_to_dict,
    paper_shadow_activation_plan_from_dict,
    paper_shadow_activation_plan_to_dict,
    sleeve_admission_release_pack_from_dict,
    sleeve_admission_release_pack_to_dict,
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
    build_sleeve_portfolio_snapshot,
)
from crypto_core.service.sleeve_promotion_review_controller import (
    SleevePromotionReviewPortfolioSummary,
    SleevePromotionReviewResult,
    SleevePromotionReviewSnapshot,
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


def _promotion_snapshot(summary: SleevePromotionReviewPortfolioSummary) -> SleevePromotionReviewSnapshot:
    return SleevePromotionReviewSnapshot(
        as_of_ns=summary.as_of_ns,
        status="active",
        review_results=summary.review_results,
        portfolio_summary=summary,
    )


def _campaign_report(
    *,
    sleeve_ids: tuple[str, ...] = ("s1",),
    verdict: AcceptanceVerdict = AcceptanceVerdict.PASS,
    sleeve_link_available: bool = True,
    persisted_tca_count: int = 8,
    completed_markout_count: int = 8,
    ext_regime_available: bool = True,
    ext_regime_evidence_sufficient: bool = True,
    ext_regime_scenario_available: bool = True,
    ext_regime_scenario_step_count: int = 6,
    ext_regime_execution_blocked_steps: int = 0,
    ext_regime_activation_blocked_steps: int = 0,
    ext_regime_activation_reduced_steps: int = 0,
    ext_regime_stale_steps: int = 1,
    ext_regime_unavailable_steps: int = 0,
    ext_regime_high_risk_steps: int = 1,
    ext_regime_safe_steps: int = 4,
    ext_regime_high_risk: bool = False,
) -> CampaignReport:
    snapshot = CampaignSnapshot(
        campaign_id="camp-release",
        status="completed",
        started_at_ns=_T0_NS - 100,
        updated_at_ns=_T0_NS,
        elapsed_seconds=100.0,
        run_id="run-release",
        service_mode="running",
        session_mode="running",
        total_events_enqueued=1_000,
        total_events_dropped=0,
        total_cycles=200,
        approved_cycles=190,
        blocked_cycles=5,
        failed_cycles=5,
        total_fills=30,
        queue_overflows=0,
        watchdog_stalls=0,
        service_restarts=0,
        persistence_failures=0,
        symbol_count=2,
        symbols_ready=2,
        symbols_blocked=0,
        symbols_with_events=2,
        symbols_with_cycles=2,
        readiness_level="paper_live",
        health_trend="stable",
        persistence_status="healthy",
        nav_usd=10_000.0,
        last_error=None,
        completed_markout_count=completed_markout_count,
        persisted_tca_count=persisted_tca_count,
        registered_fill_count=max(completed_markout_count, 30),
        ext_regime_available=ext_regime_available,
        ext_regime_fresh=True,
        ext_regime_high_risk=ext_regime_high_risk,
        ext_regime_evidence_sufficient=ext_regime_evidence_sufficient,
        ext_regime_scenario_available=ext_regime_scenario_available,
        ext_regime_scenario_step_count=ext_regime_scenario_step_count,
        ext_regime_execution_blocked_steps=ext_regime_execution_blocked_steps,
        ext_regime_activation_blocked_steps=ext_regime_activation_blocked_steps,
        ext_regime_activation_reduced_steps=ext_regime_activation_reduced_steps,
        ext_regime_stale_steps=ext_regime_stale_steps,
        ext_regime_unavailable_steps=ext_regime_unavailable_steps,
        ext_regime_high_risk_steps=ext_regime_high_risk_steps,
        ext_regime_safe_steps=ext_regime_safe_steps,
        ext_regime_scenario_summary="steps=6; safe=4; stale=1; high_risk=1; reduced=0",
        sleeve_link=CampaignSleeveLinkSummary(
            linkage_available=sleeve_link_available,
            configured_sleeve_ids=sleeve_ids if sleeve_link_available else (),
            qualified_sleeve_ids=sleeve_ids if sleeve_link_available else (),
            recommended_sleeve_ids=sleeve_ids if sleeve_link_available else (),
            blocked_sleeve_ids=(),
            summary="release pack sleeve link",
        ),
    )
    acceptance = AcceptanceResult(
        verdict=verdict,
        criteria=(
            CriterionResult(
                name="release_pack_campaign",
                passed=verdict in {AcceptanceVerdict.PASS, AcceptanceVerdict.PASS_WITH_WARNINGS},
                severity="hard",
                actual=1.0,
                threshold=1.0,
                message="release pack campaign evidence",
            ),
        ),
        failed_criteria=(),
        warning_criteria=(),
        insufficient_criteria=(),
        summary="release pack campaign evidence",
    )
    return CampaignReport(
        campaign_id="camp-release",
        status="completed",
        verdict=verdict.value,
        started_at_ns=_T0_NS - 100,
        completed_at_ns=_T0_NS,
        elapsed_seconds=100.0,
        run_id="run-release",
        snapshot=snapshot,
        acceptance=acceptance,
        symbol_participation=(),
        config={},
        ext_regime_available=ext_regime_available,
        ext_regime_fresh=True,
        ext_regime_high_risk=ext_regime_high_risk,
        ext_regime_evidence_sufficient=ext_regime_evidence_sufficient,
        ext_regime_scenario_available=ext_regime_scenario_available,
        ext_regime_scenario_step_count=ext_regime_scenario_step_count,
        ext_regime_execution_blocked_steps=ext_regime_execution_blocked_steps,
        ext_regime_activation_blocked_steps=ext_regime_activation_blocked_steps,
        ext_regime_activation_reduced_steps=ext_regime_activation_reduced_steps,
        ext_regime_stale_steps=ext_regime_stale_steps,
        ext_regime_unavailable_steps=ext_regime_unavailable_steps,
        ext_regime_high_risk_steps=ext_regime_high_risk_steps,
        ext_regime_safe_steps=ext_regime_safe_steps,
        ext_regime_scenario_summary="steps=6; safe=4; stale=1; high_risk=1; reduced=0",
        sleeve_link=snapshot.sleeve_link,
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


def _portfolio(*sleeves: CryptoSleeveState, readiness_is_supportive: bool = True) -> SleevePortfolioSnapshot:
    return SleevePortfolioSnapshot(
        as_of_ns=_T0_NS,
        sleeves=tuple(sleeves),
        readiness_level="paper_live" if readiness_is_supportive else "not_assessed",
        readiness_is_supportive=readiness_is_supportive,
    )


def _built_portfolio(*sleeves: CryptoSleeveState, readiness_is_supportive: bool = True) -> SleevePortfolioSnapshot:
    return build_sleeve_portfolio_snapshot(
        sleeves=tuple(sleeves),
        as_of_ns=_T0_NS,
        readiness_level="paper_live" if readiness_is_supportive else "not_assessed",
        readiness_is_supportive=readiness_is_supportive,
    )


def _ready_release_pack(
    *sleeves: CryptoSleeveState,
    campaign_report: CampaignReport | None = None,
):
    portfolio = _portfolio(*sleeves)
    review_summary = _review_summary(*(_review_result(sleeve.sleeve_id) for sleeve in sleeves))
    promotion_snapshot = _promotion_snapshot(review_summary)
    admission = SleeveAdmissionController(review_summary, portfolio_snapshot=portfolio).snapshot()
    report = campaign_report or _campaign_report(sleeve_ids=tuple(sleeve.sleeve_id for sleeve in sleeves))
    pack = build_sleeve_admission_release_pack(
        admission,
        promotion_review_snapshot=promotion_snapshot,
        portfolio_snapshot=portfolio,
        campaign_report=report,
        readiness_flags=campaign_readiness_flags(report),
    )
    return pack, portfolio


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


def test_restore_fail_closed_on_timestamp_drift() -> None:
    controller = SleeveAdmissionController(
        _review_summary(_review_result("s1")),
        portfolio_snapshot=_portfolio(_sleeve("s1")),
    )
    payload = sleeve_admission_snapshot_to_dict(controller.finalize())
    payload["as_of_ns"] += 1

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


def test_release_pack_model_construction_and_ready_full_admission() -> None:
    review_summary = _review_summary(_review_result("active"), _review_result("idle"))
    portfolio = _portfolio(
        _sleeve("active"),
        _sleeve(
            "idle",
            status=CryptoSleeveStatus.ENABLED,
            recommendation_status=SleeveRecommendationStatus.ELIGIBLE_BUT_NOT_SELECTED,
            decision_status=SleeveDecisionPackStatus.ELIGIBLE_BUT_NOT_SELECTED,
            effective_allocation=0.0,
        ),
    )
    admission = SleeveAdmissionController(
        review_summary,
        portfolio_snapshot=portfolio,
    ).snapshot()

    pack = build_sleeve_admission_release_pack(
        admission,
        promotion_review_snapshot=_promotion_snapshot(review_summary),
        portfolio_snapshot=portfolio,
        campaign_report=_campaign_report(sleeve_ids=("active", "idle")),
    )

    assert pack.overall_release_status == SleeveAdmissionReleaseStatus.READY_FOR_PAPER_MANAGED_SET
    assert pack.evidence_gate_status == SleeveAdmissionReleaseEvidenceStatus.EVIDENCE_READY
    assert pack.paper_campaign_evidence_available is True
    assert pack.sleeve_campaign_link_available is True
    assert pack.promotion_review_evidence_available is True
    assert pack.readiness_evidence_supportive is True
    assert pack.tca_or_markout_evidence_supportive is True
    assert pack.external_regime_evidence_supportive is True
    assert pack.admitted_sleeves == ("active", "idle")
    assert pack.admitted_active_sleeves == ("active",)
    assert pack.admitted_unallocated_sleeves == ("idle",)
    assert pack.pack_id.startswith("sleeve-admission-release-")


def test_release_pack_missing_campaign_evidence_is_not_ready() -> None:
    review_summary = _review_summary(_review_result("s1"))
    portfolio = _portfolio(_sleeve("s1"))
    admission = SleeveAdmissionController(review_summary, portfolio_snapshot=portfolio).snapshot()

    pack = build_sleeve_admission_release_pack(
        admission,
        promotion_review_snapshot=_promotion_snapshot(review_summary),
        portfolio_snapshot=portfolio,
    )

    assert pack.overall_release_status == SleeveAdmissionReleaseStatus.PARTIAL_READY
    assert pack.evidence_gate_status == SleeveAdmissionReleaseEvidenceStatus.EVIDENCE_MISSING
    assert "paper_campaign_evidence_unavailable" in pack.paper_evidence_blockers


def test_release_pack_missing_sleeve_campaign_link_is_not_ready() -> None:
    review_summary = _review_summary(_review_result("s1"))
    portfolio = _portfolio(_sleeve("s1", campaign_status=SleeveCampaignEvidenceStatus.INSUFFICIENT_EVIDENCE))
    admission = SleeveAdmissionController(review_summary, portfolio_snapshot=portfolio).snapshot()

    pack = build_sleeve_admission_release_pack(
        admission,
        promotion_review_snapshot=_promotion_snapshot(review_summary),
        portfolio_snapshot=portfolio,
        campaign_report=_campaign_report(sleeve_ids=("other",)),
    )

    assert pack.overall_release_status == SleeveAdmissionReleaseStatus.PARTIAL_READY
    assert pack.sleeve_campaign_link_available is False
    assert "sleeve_campaign_link_unavailable" in pack.paper_evidence_blockers
    assert pack.per_sleeve_evidence_blockers[0].evidence_blockers == ("sleeve_campaign_link_unavailable",)


def test_release_pack_missing_promotion_review_evidence_is_not_ready() -> None:
    review_summary = _review_summary(_review_result("s1"))
    portfolio = _portfolio(_sleeve("s1"))
    admission = SleeveAdmissionController(review_summary, portfolio_snapshot=portfolio).snapshot()

    pack = build_sleeve_admission_release_pack(
        admission,
        portfolio_snapshot=portfolio,
        campaign_report=_campaign_report(sleeve_ids=("s1",)),
    )

    assert pack.overall_release_status == SleeveAdmissionReleaseStatus.PARTIAL_READY
    assert pack.promotion_review_evidence_available is False
    assert "promotion_review_evidence_unavailable" in pack.paper_evidence_blockers


def test_release_pack_missing_readiness_support_is_not_ready() -> None:
    review_summary = _review_summary(_review_result("s1"))
    portfolio = _portfolio(_sleeve("s1"), readiness_is_supportive=False)
    admission = SleeveAdmissionController(review_summary, portfolio_snapshot=portfolio).snapshot()

    pack = build_sleeve_admission_release_pack(
        admission,
        promotion_review_snapshot=_promotion_snapshot(review_summary),
        portfolio_snapshot=portfolio,
        campaign_report=_campaign_report(sleeve_ids=("s1",)),
    )

    assert pack.overall_release_status == SleeveAdmissionReleaseStatus.PARTIAL_READY
    assert pack.evidence_gate_status == SleeveAdmissionReleaseEvidenceStatus.EVIDENCE_PARTIAL
    assert "readiness_evidence_not_supportive" in pack.paper_evidence_blockers


def test_release_pack_partial_without_tca_or_markout_evidence() -> None:
    review_summary = _review_summary(_review_result("s1"))
    portfolio = _portfolio(_sleeve("s1"))
    admission = SleeveAdmissionController(review_summary, portfolio_snapshot=portfolio).snapshot()

    pack = build_sleeve_admission_release_pack(
        admission,
        promotion_review_snapshot=_promotion_snapshot(review_summary),
        portfolio_snapshot=portfolio,
        campaign_report=_campaign_report(sleeve_ids=("s1",), persisted_tca_count=0, completed_markout_count=0),
    )

    assert pack.overall_release_status == SleeveAdmissionReleaseStatus.PARTIAL_READY
    assert pack.evidence_gate_status == SleeveAdmissionReleaseEvidenceStatus.EVIDENCE_PARTIAL
    assert "tca_or_markout_evidence_unavailable" in pack.paper_evidence_blockers


def test_release_pack_external_regime_blocker_blocks_portfolio() -> None:
    review_summary = _review_summary(_review_result("s1"))
    portfolio = _portfolio(_sleeve("s1"))
    admission = SleeveAdmissionController(review_summary, portfolio_snapshot=portfolio).snapshot()

    pack = build_sleeve_admission_release_pack(
        admission,
        promotion_review_snapshot=_promotion_snapshot(review_summary),
        portfolio_snapshot=portfolio,
        campaign_report=_campaign_report(
            sleeve_ids=("s1",),
            ext_regime_high_risk=True,
            ext_regime_high_risk_steps=4,
        ),
    )

    assert pack.overall_release_status == SleeveAdmissionReleaseStatus.BLOCKED
    assert pack.evidence_gate_status == SleeveAdmissionReleaseEvidenceStatus.EVIDENCE_BLOCKED
    assert "external_regime_governance_blocked" in pack.paper_evidence_blockers


def test_release_pack_no_candidates_and_inconclusive_states() -> None:
    empty = build_sleeve_admission_release_pack(SleeveAdmissionController().snapshot())
    review_only = build_sleeve_admission_release_pack(
        SleeveAdmissionController(_review_summary(_review_result("review-only"))).snapshot()
    )
    hold = build_sleeve_admission_release_pack(
        SleeveAdmissionController(
            _review_summary(_review_result("hold", SleevePromotionReviewVerdict.HOLD)),
            portfolio_snapshot=_portfolio(_sleeve("hold", effective_allocation=0.0)),
        ).snapshot()
    )

    assert empty.overall_release_status == SleeveAdmissionReleaseStatus.NO_CANDIDATES
    assert empty.next_actions == ()
    assert review_only.overall_release_status == SleeveAdmissionReleaseStatus.INCONCLUSIVE
    assert review_only.review_supported_not_admitted_sleeves == ("review-only",)
    assert hold.overall_release_status == SleeveAdmissionReleaseStatus.INCONCLUSIVE
    assert hold.inconclusive_sleeves == ("hold",)


def test_release_pack_partial_and_blocked_portfolio_states() -> None:
    partial = build_sleeve_admission_release_pack(
        SleeveAdmissionController(
            _review_summary(
                _review_result("active"),
                _review_result("blocked", SleevePromotionReviewVerdict.REJECT),
            ),
            portfolio_snapshot=_portfolio(
                _sleeve("active"),
                _sleeve(
                    "blocked",
                    status=CryptoSleeveStatus.BLOCKED,
                    recommendation_status=SleeveRecommendationStatus.BLOCKED,
                    qualification_status=SleeveQualificationStatus.BLOCKED,
                    campaign_status=SleeveCampaignEvidenceStatus.BLOCKED_BY_GOVERNANCE,
                    support_status=SleevePromotionSupportStatus.BLOCKED,
                    candidate_status=SleevePromotionCandidateStatus.BLOCKED,
                    decision_status=SleeveDecisionPackStatus.BLOCKED,
                    blockers=("gov_hold",),
                ),
            ),
        ).snapshot()
    )
    blocked = build_sleeve_admission_release_pack(
        SleeveAdmissionController(
            _review_summary(_review_result("blocked", SleevePromotionReviewVerdict.REJECT)),
            portfolio_snapshot=_portfolio(_sleeve("blocked", status=CryptoSleeveStatus.BLOCKED, blockers=("gov",))),
        ).snapshot()
    )

    assert partial.overall_release_status == SleeveAdmissionReleaseStatus.PARTIAL_READY
    assert partial.admitted_sleeves == ("active",)
    assert partial.blocked_sleeves == ("blocked",)
    assert blocked.overall_release_status == SleeveAdmissionReleaseStatus.BLOCKED


def test_release_pack_next_actions_and_blocker_aggregation_are_stable() -> None:
    admission = SleeveAdmissionController(
        _review_summary(
            _review_result(
                "s1",
                governance_blockers=("z_governance",),
                missing_evidence=("z_evidence",),
            )
        ),
        portfolio_snapshot=_portfolio(_sleeve("s1", missing_evidence=("a_evidence",), blockers=("a_governance",))),
    ).snapshot()

    pack = build_sleeve_admission_release_pack(admission)
    rendered = sleeve_admission_release_pack_to_dict(pack)

    assert pack.overall_release_status == SleeveAdmissionReleaseStatus.INCONCLUSIVE
    assert "a_evidence" in pack.evidence_blockers
    assert "z_evidence" in pack.evidence_blockers
    assert "paper_campaign_evidence_unavailable" in pack.evidence_blockers
    assert pack.governance_blockers == ("a_governance", "z_governance")
    assert pack.next_actions[0].next_action == "continue_paper_review"
    assert rendered["next_actions"][0]["admission_verdict"] == "review_supported_not_admitted"
    assert rendered["evidence_gate_status"] == "evidence_missing"
    assert rendered == sleeve_admission_release_pack_to_dict(pack)


def test_release_pack_serialization_roundtrip_and_backward_defaults() -> None:
    admission = SleeveAdmissionController(
        _review_summary(_review_result("s1")),
        portfolio_snapshot=_portfolio(_sleeve("s1")),
    ).snapshot()
    pack = build_sleeve_admission_release_pack(admission)
    payload = sleeve_admission_release_pack_to_dict(pack)

    restored = sleeve_admission_release_pack_from_dict(payload)
    legacy = sleeve_admission_release_pack_from_dict({"portfolio_summary": payload["portfolio_summary"]})

    assert restored == pack
    assert legacy.overall_release_status == SleeveAdmissionReleaseStatus.PARTIAL_READY
    assert legacy.evidence_gate_status == SleeveAdmissionReleaseEvidenceStatus.EVIDENCE_MISSING
    assert legacy.admitted_sleeves == ("s1",)
    assert legacy.admission_snapshot_status == "unknown"


def test_release_pack_malformed_payload_fails_closed() -> None:
    admission = SleeveAdmissionController(
        _review_summary(_review_result("s1")),
        portfolio_snapshot=_portfolio(_sleeve("s1")),
    ).snapshot()
    payload = sleeve_admission_release_pack_to_dict(build_sleeve_admission_release_pack(admission))
    payload["overall_release_status"] = "blocked"

    with pytest.raises(SleeveAdmissionCorruptError):
        sleeve_admission_release_pack_from_dict(payload)


def test_release_pack_artifact_export_load_roundtrip_and_bad_load_fail_closed(tmp_path) -> None:
    store = EvidenceStore(evidence_dir=tmp_path / "evidence", config=EvidenceStoreConfig())
    admission = SleeveAdmissionController(
        _review_summary(_review_result("s1")),
        portfolio_snapshot=_portfolio(_sleeve("s1")),
    ).snapshot()
    pack = build_sleeve_admission_release_pack(admission)

    export_sleeve_admission_release_pack(pack=pack, evidence_store=store)
    restored = load_sleeve_admission_release_pack(evidence_store=store)

    assert restored == pack

    store.save_snapshot("crypto_sleeve_admission_release_pack", ["bad"])
    with pytest.raises(SleeveAdmissionCorruptError):
        load_sleeve_admission_release_pack(evidence_store=store)


def test_service_orchestrator_release_pack_helper_and_operator_compact_status() -> None:
    fixed_review_ns = _T0_NS + 42
    orch = ServiceOrchestrator(
        service=_mock_service(),
        sleeves=(_sleeve("svc-sleeve", effective_allocation=0.20, target_allocation=0.20),),
        readiness_level="paper_live",
        sleeve_workflow_clock_ns=lambda: fixed_review_ns,
    )
    campaign_report = _campaign_report(sleeve_ids=("svc-sleeve",))
    orch._last_campaign_report = campaign_report  # type: ignore[attr-defined]
    orch.start_sleeve_promotion_review(workflow_snapshot=_supported_workflow("svc-sleeve"))

    pack = orch.sleeve_admission_release_pack(
        portfolio_snapshot=_portfolio(_sleeve("svc-sleeve", effective_allocation=0.20, target_allocation=0.20)),
        campaign_report=campaign_report,
        readiness_flags=campaign_readiness_flags(campaign_report),
    )
    rendered = sleeve_admission_release_pack_to_dict(pack)
    helper_rendered = orch.sleeve_admission_release_pack_dict()

    assert pack.as_of_ns == fixed_review_ns
    assert pack.overall_release_status == SleeveAdmissionReleaseStatus.READY_FOR_PAPER_MANAGED_SET
    assert pack.evidence_gate_status == SleeveAdmissionReleaseEvidenceStatus.EVIDENCE_READY
    assert rendered["overall_release_status"] == "ready_for_paper_managed_set"
    assert rendered["evidence_gate_status"] == "evidence_ready"
    assert helper_rendered["overall_release_status"] == "inconclusive"
    assert helper_rendered["evidence_gate_status"] == "evidence_missing"

    operator = operator_snapshot_to_dict(orch.operator_snapshot())
    assert operator["sleeve_admission_release"]["overall_release_status"] == "inconclusive"
    assert operator["sleeve_admission_release"]["evidence_gate_status"] == "evidence_missing"
    assert operator["sleeve_admission_release"]["paper_campaign_evidence_available"] is True
    assert operator["sleeve_admission_release"]["available"] is True


def test_service_orchestrator_release_pack_export_load_helper(tmp_path) -> None:
    fixed_review_ns = _T0_NS + 77
    store = EvidenceStore(evidence_dir=tmp_path / "evidence", config=EvidenceStoreConfig())
    orch = ServiceOrchestrator(
        service=_mock_service(),
        evidence_store=store,
        sleeve_workflow_clock_ns=lambda: fixed_review_ns,
    )
    orch.start_sleeve_promotion_review(workflow_snapshot=_supported_workflow("export-sleeve"))

    orch.export_sleeve_admission_release_pack()
    loaded = orch.load_sleeve_admission_release_pack()

    assert loaded == orch.sleeve_admission_release_pack()
    assert loaded.source_promotion_review_as_of_ns == fixed_review_ns


def test_release_pack_deterministic_replay_with_fixed_clock() -> None:
    fixed_review_ns = _T0_NS + 123
    portfolio = _portfolio(_sleeve("stable", effective_allocation=0.10))
    orch = ServiceOrchestrator(service=_mock_service(), sleeve_workflow_clock_ns=lambda: fixed_review_ns)
    orch.start_sleeve_promotion_review(workflow_snapshot=_supported_workflow("stable"))

    first = sleeve_admission_release_pack_to_dict(orch.sleeve_admission_release_pack(portfolio_snapshot=portfolio))
    second = sleeve_admission_release_pack_to_dict(orch.sleeve_admission_release_pack(portfolio_snapshot=portfolio))

    assert first == second
    assert first["source_promotion_review_as_of_ns"] == fixed_review_ns


def test_managed_manifest_model_construction_and_ready_dry_run() -> None:
    sleeve = _sleeve("active", effective_allocation=0.25, target_allocation=0.25)
    pack, _ = _ready_release_pack(sleeve)

    manifest = build_managed_sleeve_set_manifest(pack)
    portfolio_manifest = build_managed_sleeve_set_manifest(pack, portfolio_snapshot=_built_portfolio(sleeve))
    rendered = managed_sleeve_set_manifest_to_dict(manifest)

    assert manifest.dry_run_status == ManagedSleeveSetDryRunStatus.READY_FOR_PAPER_DRY_RUN
    assert portfolio_manifest.dry_run_status == ManagedSleeveSetDryRunStatus.READY_FOR_PAPER_DRY_RUN
    assert manifest.source_release_pack_status == SleeveAdmissionReleaseStatus.READY_FOR_PAPER_MANAGED_SET
    assert manifest.source_evidence_gate_status == SleeveAdmissionReleaseEvidenceStatus.EVIDENCE_READY
    assert manifest.active_sleeves == ("active",)
    assert rendered["effective_allocations"] == [{"sleeve_id": "active", "effective_allocation": 0.25}]
    assert rendered["unallocated_share"] == 0.75
    assert portfolio_manifest.unallocated_share == 0.75
    assert rendered["activation_blockers"] == []
    assert manifest.source_release_pack_hash
    assert manifest.manifest_id.startswith("managed-sleeve-set-manifest-")


def test_managed_manifest_empty_release_pack_is_empty_and_blocked_safe() -> None:
    pack = build_sleeve_admission_release_pack(SleeveAdmissionController().snapshot())

    manifest = build_managed_sleeve_set_manifest(pack)

    assert manifest.dry_run_status == ManagedSleeveSetDryRunStatus.EMPTY
    assert manifest.active_sleeves == ()
    assert manifest.effective_allocations == ()
    assert "no_admission_candidates" in manifest.activation_blockers


def test_managed_manifest_partial_release_pack_is_not_ready() -> None:
    portfolio = _portfolio(_sleeve("active", effective_allocation=0.20, target_allocation=0.20))
    review_summary = _review_summary(_review_result("active"))
    admission = SleeveAdmissionController(review_summary, portfolio_snapshot=portfolio).snapshot()
    pack = build_sleeve_admission_release_pack(
        admission,
        promotion_review_snapshot=_promotion_snapshot(review_summary),
        portfolio_snapshot=portfolio,
    )

    manifest = build_managed_sleeve_set_manifest(pack)

    assert pack.overall_release_status == SleeveAdmissionReleaseStatus.PARTIAL_READY
    assert manifest.dry_run_status == ManagedSleeveSetDryRunStatus.PARTIAL_PAPER_DRY_RUN
    assert "release_pack_evidence_not_ready" in manifest.activation_blockers


def test_managed_manifest_tracks_unallocated_and_excludes_blocked_sleeves() -> None:
    active = _sleeve("active", effective_allocation=0.30, target_allocation=0.30)
    reserve = _sleeve(
        "reserve",
        status=CryptoSleeveStatus.ENABLED,
        recommendation_status=SleeveRecommendationStatus.ELIGIBLE_BUT_NOT_SELECTED,
        decision_status=SleeveDecisionPackStatus.ELIGIBLE_BUT_NOT_SELECTED,
        effective_allocation=0.0,
        target_allocation=0.0,
    )
    blocked = _sleeve(
        "blocked",
        status=CryptoSleeveStatus.BLOCKED,
        recommendation_status=SleeveRecommendationStatus.BLOCKED,
        qualification_status=SleeveQualificationStatus.BLOCKED,
        campaign_status=SleeveCampaignEvidenceStatus.BLOCKED_BY_GOVERNANCE,
        support_status=SleevePromotionSupportStatus.BLOCKED,
        candidate_status=SleevePromotionCandidateStatus.BLOCKED,
        decision_status=SleeveDecisionPackStatus.BLOCKED,
        effective_allocation=0.0,
        target_allocation=0.0,
        blockers=("governance_block",),
    )
    portfolio = _portfolio(active, reserve, blocked)
    review_summary = _review_summary(
        _review_result("active"),
        _review_result("reserve"),
        _review_result("blocked", SleevePromotionReviewVerdict.REJECT, governance_blockers=("review_block",)),
    )
    report = _campaign_report(sleeve_ids=("active", "reserve", "blocked"))
    admission = SleeveAdmissionController(review_summary, portfolio_snapshot=portfolio).snapshot()
    pack = build_sleeve_admission_release_pack(
        admission,
        promotion_review_snapshot=_promotion_snapshot(review_summary),
        portfolio_snapshot=portfolio,
        campaign_report=report,
        readiness_flags=campaign_readiness_flags(report),
    )

    manifest = build_managed_sleeve_set_manifest(pack)

    assert manifest.dry_run_status == ManagedSleeveSetDryRunStatus.PARTIAL_PAPER_DRY_RUN
    assert manifest.active_sleeves == ("active",)
    assert manifest.admitted_unallocated_sleeves == ("reserve",)
    assert manifest.blocked_sleeves == ("blocked",)
    assert "blocked" not in manifest.active_sleeves
    assert "governance_block" in manifest.activation_blockers
    assert "review_block" in manifest.governance_blockers

    blocked_review_summary = _review_summary(_review_result("blocked", SleevePromotionReviewVerdict.REJECT))
    blocked_report = _campaign_report(sleeve_ids=("blocked",))
    blocked_admission = SleeveAdmissionController(
        blocked_review_summary,
        portfolio_snapshot=_portfolio(blocked),
    ).snapshot()
    blocked_pack = build_sleeve_admission_release_pack(
        blocked_admission,
        promotion_review_snapshot=_promotion_snapshot(blocked_review_summary),
        portfolio_snapshot=_portfolio(blocked),
        campaign_report=blocked_report,
        readiness_flags=campaign_readiness_flags(blocked_report),
    )
    blocked_manifest = build_managed_sleeve_set_manifest(blocked_pack)
    assert blocked_manifest.dry_run_status == ManagedSleeveSetDryRunStatus.BLOCKED


def test_managed_manifest_next_actions_and_serialization_roundtrip() -> None:
    active = _sleeve("z-active", effective_allocation=0.10, target_allocation=0.10)
    reserve = _sleeve(
        "a-reserve",
        status=CryptoSleeveStatus.ENABLED,
        recommendation_status=SleeveRecommendationStatus.ELIGIBLE_BUT_NOT_SELECTED,
        decision_status=SleeveDecisionPackStatus.ELIGIBLE_BUT_NOT_SELECTED,
        effective_allocation=0.0,
        target_allocation=0.0,
    )
    pack, _ = _ready_release_pack(active, reserve)

    manifest = build_managed_sleeve_set_manifest(pack)
    rendered = managed_sleeve_set_manifest_to_dict(manifest)
    restored = managed_sleeve_set_manifest_from_dict(rendered)

    assert restored == manifest
    assert manifest.active_sleeves == ("z-active",)
    assert manifest.admitted_unallocated_sleeves == ("a-reserve",)
    assert [item["sleeve_id"] for item in rendered["next_actions"]] == ["a-reserve", "z-active"]
    assert (
        manifest.operator_summary
        == "dry_run_status=ready_for_paper_dry_run; active=1; admitted_unallocated=1; blocked=0"
    )


def test_managed_manifest_old_payload_degrades_without_effective_allocations() -> None:
    manifest = managed_sleeve_set_manifest_from_dict(
        {
            "source_release_pack_status": "ready_for_paper_managed_set",
            "active_sleeves": ["legacy-active"],
        }
    )

    assert manifest.dry_run_status == ManagedSleeveSetDryRunStatus.EMPTY
    assert manifest.active_sleeves == ()
    assert manifest.source_evidence_gate_status == SleeveAdmissionReleaseEvidenceStatus.EVIDENCE_MISSING
    assert "no_admission_candidates" in manifest.activation_blockers


def test_managed_manifest_malformed_load_fails_closed(tmp_path) -> None:
    pack, _ = _ready_release_pack(_sleeve("active", effective_allocation=0.25, target_allocation=0.25))
    manifest = build_managed_sleeve_set_manifest(pack)
    payload = managed_sleeve_set_manifest_to_dict(manifest)
    payload["dry_run_status"] = "blocked"

    with pytest.raises(SleeveAdmissionCorruptError):
        managed_sleeve_set_manifest_from_dict(payload)

    store = EvidenceStore(evidence_dir=tmp_path / "evidence", config=EvidenceStoreConfig())
    export_managed_sleeve_set_manifest(manifest=manifest, evidence_store=store)
    assert load_managed_sleeve_set_manifest(evidence_store=store) == manifest

    store.save_snapshot("crypto_managed_sleeve_set_manifest", ["bad"])
    with pytest.raises(SleeveAdmissionCorruptError):
        load_managed_sleeve_set_manifest(evidence_store=store)


def test_service_orchestrator_managed_manifest_helpers_and_operator_status(tmp_path) -> None:
    fixed_review_ns = _T0_NS + 321
    store = EvidenceStore(evidence_dir=tmp_path / "evidence", config=EvidenceStoreConfig())
    sleeve = _sleeve("svc-active", effective_allocation=0.20, target_allocation=0.20)
    portfolio = _built_portfolio(sleeve)
    pack, _ = _ready_release_pack(sleeve)
    orch = ServiceOrchestrator(
        service=_mock_service(),
        sleeves=(sleeve,),
        evidence_store=store,
        readiness_level="paper_live",
        sleeve_workflow_clock_ns=lambda: fixed_review_ns,
    )
    orch._last_campaign_report = _campaign_report(sleeve_ids=("svc-active",))  # type: ignore[attr-defined]
    orch.start_sleeve_promotion_review(workflow_snapshot=_supported_workflow("svc-active"))

    manifest = orch.managed_sleeve_set_manifest(release_pack=pack, portfolio_snapshot=portfolio)
    rendered = orch.managed_sleeve_set_manifest_dict()
    operator = operator_snapshot_to_dict(orch.operator_snapshot())

    assert manifest.dry_run_status == ManagedSleeveSetDryRunStatus.READY_FOR_PAPER_DRY_RUN
    assert rendered["dry_run_status"] in {"ready_for_paper_dry_run", "partial_paper_dry_run", "inconclusive"}
    assert operator["managed_sleeve_manifest"]["available"] is True
    assert "dry_run_status" in operator["managed_sleeve_manifest"]

    orch.export_managed_sleeve_set_manifest()
    assert orch.load_managed_sleeve_set_manifest() == orch.managed_sleeve_set_manifest()


def test_managed_manifest_deterministic_replay() -> None:
    pack, _ = _ready_release_pack(_sleeve("stable", effective_allocation=0.15, target_allocation=0.15))

    first = managed_sleeve_set_manifest_to_dict(build_managed_sleeve_set_manifest(pack))
    second = managed_sleeve_set_manifest_to_dict(build_managed_sleeve_set_manifest(pack))

    assert first == second
    assert first["source_release_pack_hash"] == second["source_release_pack_hash"]


def test_paper_shadow_activation_plan_model_construction_and_ready_status() -> None:
    active = _sleeve("active", effective_allocation=0.25, target_allocation=0.25)
    pack, _ = _ready_release_pack(active)
    manifest = build_managed_sleeve_set_manifest(pack)

    plan = build_paper_shadow_activation_plan(manifest)
    rendered = paper_shadow_activation_plan_to_dict(plan)

    assert plan.activation_status == PaperShadowActivationStatus.READY_FOR_PAPER_SHADOW
    assert plan.source_manifest_status == ManagedSleeveSetDryRunStatus.READY_FOR_PAPER_DRY_RUN
    assert plan.paper_only is True
    assert plan.real_orders_enabled is False
    assert plan.real_money_enabled is False
    assert plan.active_sleeves == ("active",)
    assert plan.inactive_sleeves == ()
    assert rendered["effective_allocations"] == [{"sleeve_id": "active", "effective_allocation": 0.25}]
    assert "paper_only_mode_confirmed" in plan.preflight_gates
    assert "record_paper_shadow_artifacts" in plan.runtime_monitoring_requirements
    assert "operator_can_disable_sleeve" in plan.kill_switch_requirements
    assert plan.source_manifest_hash
    assert plan.plan_id.startswith("paper-shadow-activation-plan-")


def test_paper_shadow_activation_plan_empty_manifest_is_empty_safe() -> None:
    manifest = build_managed_sleeve_set_manifest(
        build_sleeve_admission_release_pack(SleeveAdmissionController().snapshot())
    )

    plan = build_paper_shadow_activation_plan(manifest)

    assert plan.activation_status == PaperShadowActivationStatus.EMPTY
    assert plan.active_sleeves == ()
    assert plan.effective_allocations == ()
    assert "source_manifest_empty" in plan.activation_blockers
    assert plan.paper_only is True
    assert plan.real_orders_enabled is False
    assert plan.real_money_enabled is False


def test_paper_shadow_activation_plan_partial_manifest_is_not_ready() -> None:
    portfolio = _portfolio(_sleeve("active", effective_allocation=0.20, target_allocation=0.20))
    review_summary = _review_summary(_review_result("active"))
    admission = SleeveAdmissionController(review_summary, portfolio_snapshot=portfolio).snapshot()
    pack = build_sleeve_admission_release_pack(
        admission,
        promotion_review_snapshot=_promotion_snapshot(review_summary),
        portfolio_snapshot=portfolio,
    )
    manifest = build_managed_sleeve_set_manifest(pack)

    plan = build_paper_shadow_activation_plan(manifest)

    assert manifest.dry_run_status == ManagedSleeveSetDryRunStatus.PARTIAL_PAPER_DRY_RUN
    assert plan.activation_status == PaperShadowActivationStatus.PARTIAL_READY
    assert "source_manifest_not_ready_for_paper_shadow" in plan.activation_blockers
    assert "release_pack_evidence_not_ready" in plan.activation_blockers


def test_paper_shadow_activation_plan_blocked_manifest_is_blocked() -> None:
    blocked = _sleeve(
        "blocked",
        status=CryptoSleeveStatus.BLOCKED,
        recommendation_status=SleeveRecommendationStatus.BLOCKED,
        qualification_status=SleeveQualificationStatus.BLOCKED,
        campaign_status=SleeveCampaignEvidenceStatus.BLOCKED_BY_GOVERNANCE,
        support_status=SleevePromotionSupportStatus.BLOCKED,
        candidate_status=SleevePromotionCandidateStatus.BLOCKED,
        decision_status=SleeveDecisionPackStatus.BLOCKED,
        effective_allocation=0.0,
        target_allocation=0.0,
        blockers=("governance_block",),
    )
    review_summary = _review_summary(_review_result("blocked", SleevePromotionReviewVerdict.REJECT))
    report = _campaign_report(sleeve_ids=("blocked",))
    admission = SleeveAdmissionController(review_summary, portfolio_snapshot=_portfolio(blocked)).snapshot()
    pack = build_sleeve_admission_release_pack(
        admission,
        promotion_review_snapshot=_promotion_snapshot(review_summary),
        portfolio_snapshot=_portfolio(blocked),
        campaign_report=report,
        readiness_flags=campaign_readiness_flags(report),
    )
    manifest = build_managed_sleeve_set_manifest(pack)

    plan = build_paper_shadow_activation_plan(manifest)

    assert plan.activation_status == PaperShadowActivationStatus.BLOCKED
    assert plan.active_sleeves == ()
    assert "blocked" in plan.inactive_sleeves
    assert "governance_blockers_present" in plan.activation_blockers


def test_paper_shadow_activation_plan_tracks_unallocated_and_allocations() -> None:
    active = _sleeve("z-active", effective_allocation=0.10, target_allocation=0.10)
    reserve = _sleeve(
        "a-reserve",
        status=CryptoSleeveStatus.ENABLED,
        recommendation_status=SleeveRecommendationStatus.ELIGIBLE_BUT_NOT_SELECTED,
        decision_status=SleeveDecisionPackStatus.ELIGIBLE_BUT_NOT_SELECTED,
        effective_allocation=0.0,
        target_allocation=0.0,
    )
    pack, _ = _ready_release_pack(active, reserve)
    manifest = build_managed_sleeve_set_manifest(pack)

    plan = build_paper_shadow_activation_plan(manifest)

    assert plan.activation_status == PaperShadowActivationStatus.READY_FOR_PAPER_SHADOW
    assert plan.active_sleeves == ("z-active",)
    assert plan.inactive_sleeves == ("a-reserve",)
    assert plan.admitted_unallocated_sleeves == ("a-reserve",)
    assert plan.effective_allocations[0].sleeve_id == "z-active"
    assert plan.effective_allocations[0].effective_allocation == 0.10
    assert [action.sleeve_id for action in plan.next_actions] == ["a-reserve", "z-active"]


def test_paper_shadow_activation_plan_serialization_roundtrip_and_malformed_load(tmp_path) -> None:
    pack, _ = _ready_release_pack(_sleeve("active", effective_allocation=0.25, target_allocation=0.25))
    manifest = build_managed_sleeve_set_manifest(pack)
    plan = build_paper_shadow_activation_plan(manifest)
    payload = paper_shadow_activation_plan_to_dict(plan)

    restored = paper_shadow_activation_plan_from_dict(payload)
    assert restored == plan

    malformed = dict(payload)
    malformed["real_orders_enabled"] = True
    with pytest.raises(SleeveAdmissionCorruptError):
        paper_shadow_activation_plan_from_dict(malformed)

    store = EvidenceStore(evidence_dir=tmp_path / "evidence", config=EvidenceStoreConfig())
    export_paper_shadow_activation_plan(plan=plan, evidence_store=store)
    assert load_paper_shadow_activation_plan(evidence_store=store) == plan

    store.save_snapshot("crypto_paper_shadow_activation_plan", ["bad"])
    with pytest.raises(SleeveAdmissionCorruptError):
        load_paper_shadow_activation_plan(evidence_store=store)


def test_service_orchestrator_paper_shadow_activation_plan_helpers_and_operator_status(tmp_path) -> None:
    fixed_review_ns = _T0_NS + 654
    store = EvidenceStore(evidence_dir=tmp_path / "evidence", config=EvidenceStoreConfig())
    sleeve = _sleeve("svc-active", effective_allocation=0.20, target_allocation=0.20)
    pack, _ = _ready_release_pack(sleeve)
    manifest = build_managed_sleeve_set_manifest(pack)
    orch = ServiceOrchestrator(
        service=_mock_service(),
        sleeves=(sleeve,),
        evidence_store=store,
        readiness_level="paper_live",
        sleeve_workflow_clock_ns=lambda: fixed_review_ns,
    )
    orch._last_campaign_report = _campaign_report(sleeve_ids=("svc-active",))  # type: ignore[attr-defined]
    orch.start_sleeve_promotion_review(workflow_snapshot=_supported_workflow("svc-active"))

    plan = orch.paper_shadow_activation_plan(manifest=manifest)
    rendered = paper_shadow_activation_plan_to_dict(plan)
    helper_rendered = orch.paper_shadow_activation_plan_dict()
    operator = operator_snapshot_to_dict(orch.operator_snapshot())

    assert plan.activation_status == PaperShadowActivationStatus.READY_FOR_PAPER_SHADOW
    assert rendered["paper_only"] is True
    assert rendered["real_orders_enabled"] is False
    assert rendered["real_money_enabled"] is False
    assert "activation_status" in helper_rendered
    assert operator["paper_shadow_activation_plan"]["available"] is True
    assert operator["paper_shadow_activation_plan"]["real_orders_enabled"] is False
    assert operator["paper_shadow_activation_plan"]["real_money_enabled"] is False

    orch.export_paper_shadow_activation_plan()
    assert orch.load_paper_shadow_activation_plan() == orch.paper_shadow_activation_plan()


def test_paper_shadow_activation_plan_deterministic_replay() -> None:
    pack, _ = _ready_release_pack(_sleeve("stable", effective_allocation=0.15, target_allocation=0.15))
    manifest = build_managed_sleeve_set_manifest(pack)

    first = paper_shadow_activation_plan_to_dict(build_paper_shadow_activation_plan(manifest))
    second = paper_shadow_activation_plan_to_dict(build_paper_shadow_activation_plan(manifest))

    assert first == second
    assert first["source_manifest_hash"] == second["source_manifest_hash"]
