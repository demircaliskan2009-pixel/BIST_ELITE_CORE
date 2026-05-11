from __future__ import annotations

import json
from unittest.mock import MagicMock

from crypto_core.service.service_orchestrator import (
    EvidenceSufficiencyState,
    OperatorSnapshot,
    ServiceOrchestrator,
    operator_snapshot_to_dict,
)
from crypto_core.service.sleeve_admission_controller import (
    SleeveAdmissionHistoryEntry,
    SleeveAdmissionPortfolioSummary,
    SleeveAdmissionResult,
    SleeveAdmissionSnapshot,
    SleeveAdmissionVerdict,
)
from crypto_core.service.sleeve_promotion_review_controller import (
    SleevePromotionReviewHistoryEntry,
    SleevePromotionReviewPortfolioSummary,
    SleevePromotionReviewResult,
    SleevePromotionReviewSnapshot,
    SleevePromotionReviewVerdict,
)


def _evidence_state() -> EvidenceSufficiencyState:
    return EvidenceSufficiencyState(
        campaign_evidence_available=True,
        review_evidence_available=True,
        execution_calibration_available=True,
        promotion_evidence_sufficient=True,
        insufficient_reasons=(),
        summary="Evidence sufficient.",
    )


def _review_snapshot() -> SleevePromotionReviewSnapshot:
    result = SleevePromotionReviewResult(
        sleeve_id="sleeve-microstructure",
        verdict=SleevePromotionReviewVerdict.REVIEW_SUPPORTED,
        reason="Supportive sleeve candidate evidence.",
        next_step="Continue paper monitoring.",
        missing_evidence=("pbo:pbo_rejected",),
        governance_blockers=(),
        last_verdict=None,
        pbo_allocation_cap=0.5,
    )
    summary = SleevePromotionReviewPortfolioSummary(
        as_of_ns=101,
        review_results=(result,),
        supported=("sleeve-microstructure",),
        hold=(),
        reject=(),
        inconclusive=(),
        repeated_weak=(),
        repeated_blocked=(),
        repeated_inconclusive=(),
        missing_evidence=("pbo:pbo_rejected",),
        governance_blockers=(),
        operator_summary="Supported: ['sleeve-microstructure'].",
    )
    history = SleevePromotionReviewHistoryEntry(
        as_of_ns=101,
        summary=summary.operator_summary,
        portfolio_summary=summary,
    )
    return SleevePromotionReviewSnapshot(
        as_of_ns=101,
        status="active",
        review_results=(result,),
        portfolio_summary=summary,
        history=(history,),
    )


def _admission_snapshot() -> SleeveAdmissionSnapshot:
    result = SleeveAdmissionResult(
        sleeve_id="sleeve-microstructure",
        verdict=SleeveAdmissionVerdict.ADMITTED_UNALLOCATED,
        reason="Admitted but unallocated due to missing evidence.",
        next_step="Complete evidence for allocation.",
        governance_blockers=(),
        evidence_blockers=("pbo:pbo_rejected",),
        last_review_verdict=SleevePromotionReviewVerdict.REVIEW_SUPPORTED,
        pbo_allocation_cap=0.5,
    )
    summary = SleeveAdmissionPortfolioSummary(
        as_of_ns=202,
        admission_results=(result,),
        admitted_active=(),
        admitted_unallocated=("sleeve-microstructure",),
        review_supported_not_admitted=(),
        blocked=(),
        inconclusive=(),
        governance_blockers=(),
        evidence_blockers=("pbo:pbo_rejected",),
        operator_summary="Admitted: 0, Unallocated: 1, Supported/Blocked: 0, Blocked: 0, Inconclusive: 0",
    )
    history = SleeveAdmissionHistoryEntry(
        as_of_ns=202,
        summary=summary.operator_summary,
        portfolio_summary=summary,
    )
    return SleeveAdmissionSnapshot(
        as_of_ns=202,
        status="active",
        admission_results=(result,),
        portfolio_summary=summary,
        history=(history,),
    )


def _operator_snapshot(
    *,
    review_snapshot: SleevePromotionReviewSnapshot | None = None,
    admission_snapshot: SleeveAdmissionSnapshot | None = None,
) -> OperatorSnapshot:
    return OperatorSnapshot(
        service_mode="paper",
        trading_enabled=False,
        blocked_reason=None,
        ei_available=False,
        ei_degraded=False,
        ei_degraded_reasons=(),
        campaign=None,
        review=None,
        readiness_level="paper_live",
        readiness_is_supportive=True,
        evidence=_evidence_state(),
        provisional_recommendation=None,
        recommendation_summary="No promotion review active.",
        external_regime=None,
        external_regime_safety=None,
        external_regime_scenario=None,
        sleeve_portfolio=None,
        sleeve_candidate_workflow=None,
        sleeve_promotion_review=review_snapshot,
        sleeve_admission=admission_snapshot,
        escalation_review=None,
    )


def _make_orchestrator(snapshot: OperatorSnapshot) -> ServiceOrchestrator:
    service = MagicMock()
    orch = ServiceOrchestrator(service=service, readiness_level="paper_live")
    orch.operator_snapshot = MagicMock(return_value=snapshot)
    return orch


def test_combined_status_dict_is_json_safe_with_active_sleeve_admission():
    orch = _make_orchestrator(_operator_snapshot(admission_snapshot=_admission_snapshot()))
    payload = orch.combined_status_dict()
    serialized = json.dumps(payload)
    assert len(serialized) > 0


def test_combined_status_dict_includes_admission_evidence_blockers():
    orch = _make_orchestrator(_operator_snapshot(admission_snapshot=_admission_snapshot()))
    payload = orch.combined_status_dict()
    assert payload["sleeve_admission"]["portfolio_summary"]["evidence_blockers"] == ["pbo:pbo_rejected"]


def test_combined_status_dict_serializes_admission_pbo_allocation_cap():
    orch = _make_orchestrator(_operator_snapshot(admission_snapshot=_admission_snapshot()))
    payload = orch.combined_status_dict()
    assert payload["sleeve_admission"]["admission_results"][0]["pbo_allocation_cap"] == 0.5
    assert isinstance(payload["sleeve_admission"]["admission_results"][0]["pbo_allocation_cap"], float)


def test_combined_status_dict_serializes_admission_verdict_as_string():
    orch = _make_orchestrator(_operator_snapshot(admission_snapshot=_admission_snapshot()))
    payload = orch.combined_status_dict()
    verdict = payload["sleeve_admission"]["admission_results"][0]["verdict"]
    assert verdict == SleeveAdmissionVerdict.ADMITTED_UNALLOCATED.value
    assert isinstance(verdict, str)


def test_combined_status_dict_is_json_safe_with_active_sleeve_promotion_review():
    orch = _make_orchestrator(_operator_snapshot(review_snapshot=_review_snapshot()))
    payload = orch.combined_status_dict()
    serialized = json.dumps(payload)
    assert len(serialized) > 0


def test_combined_status_dict_includes_review_missing_evidence():
    orch = _make_orchestrator(_operator_snapshot(review_snapshot=_review_snapshot()))
    payload = orch.combined_status_dict()
    assert payload["sleeve_promotion_review"]["review_results"][0]["missing_evidence"] == ["pbo:pbo_rejected"]


def test_combined_status_dict_serializes_review_pbo_allocation_cap():
    orch = _make_orchestrator(_operator_snapshot(review_snapshot=_review_snapshot()))
    payload = orch.combined_status_dict()
    assert payload["sleeve_promotion_review"]["review_results"][0]["pbo_allocation_cap"] == 0.5
    assert isinstance(payload["sleeve_promotion_review"]["review_results"][0]["pbo_allocation_cap"], float)


def test_combined_status_dict_serializes_review_verdict_as_string():
    orch = _make_orchestrator(_operator_snapshot(review_snapshot=_review_snapshot()))
    payload = orch.combined_status_dict()
    verdict = payload["sleeve_promotion_review"]["review_results"][0]["verdict"]
    assert verdict == SleevePromotionReviewVerdict.REVIEW_SUPPORTED.value
    assert isinstance(verdict, str)


def test_existing_combined_status_dict_behavior_keeps_sleeve_review_and_admission_none():
    orch = _make_orchestrator(_operator_snapshot())
    payload = orch.combined_status_dict()
    assert payload["sleeve_promotion_review"] is None
    assert payload["sleeve_admission"] is None


def test_operator_snapshot_to_dict_is_deterministic_for_repeated_calls():
    snapshot = _operator_snapshot(
        review_snapshot=_review_snapshot(),
        admission_snapshot=_admission_snapshot(),
    )
    first = operator_snapshot_to_dict(snapshot)
    second = operator_snapshot_to_dict(snapshot)
    assert first == second
