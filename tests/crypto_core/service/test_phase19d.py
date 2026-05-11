import json
from dataclasses import dataclass, field, replace
from unittest.mock import MagicMock

from crypto_core.service.artifact_export import (
    EscalationStage,
    decision_pack_from_dict,
    decision_pack_missing_evidence,
    decision_pack_to_dict,
    export_operator_decision_pack,
    load_operator_decision_pack,
)
from crypto_core.service.evidence_store import EvidenceStore, EvidenceStoreConfig
from crypto_core.service.service_orchestrator import (
    EvidenceSufficiencyState,
    OperatorSnapshot,
    ServiceOrchestrator,
)
from crypto_core.service.sleeve_admission_controller import (
    SleeveAdmissionHistoryEntry,
    SleeveAdmissionPortfolioSummary,
    SleeveAdmissionResult,
    SleeveAdmissionSnapshot,
    SleeveAdmissionVerdict,
)
from crypto_core.service.sleeve_promotion_review_controller import SleevePromotionReviewVerdict

_STAGE4_BLOCKER = "stage4:paper_sharpe_below_backtest_threshold"
_SLEEVE_ID = "sleeve-microstructure"


def _evidence_state() -> EvidenceSufficiencyState:
    return EvidenceSufficiencyState(
        campaign_evidence_available=True,
        review_evidence_available=True,
        execution_calibration_available=True,
        promotion_evidence_sufficient=True,
        insufficient_reasons=(),
        summary="Evidence sufficient.",
        external_regime_available=True,
        external_regime_fresh=True,
    )


def _admission_snapshot(
    *,
    evidence_blockers: tuple[str, ...] = (_STAGE4_BLOCKER,),
    pbo_allocation_cap: float | None = 0.5,
) -> SleeveAdmissionSnapshot:
    result = SleeveAdmissionResult(
        sleeve_id=_SLEEVE_ID,
        verdict=SleeveAdmissionVerdict.ADMITTED_UNALLOCATED,
        reason="Admitted but unallocated due to sleeve validation evidence.",
        next_step="Complete sleeve validation evidence.",
        governance_blockers=(),
        evidence_blockers=evidence_blockers,
        last_review_verdict=SleevePromotionReviewVerdict.REVIEW_SUPPORTED,
        pbo_allocation_cap=pbo_allocation_cap,
    )
    summary = SleeveAdmissionPortfolioSummary(
        as_of_ns=202,
        admission_results=(result,),
        admitted_active=(),
        admitted_unallocated=(_SLEEVE_ID,),
        review_supported_not_admitted=(),
        blocked=(),
        inconclusive=(),
        governance_blockers=(),
        evidence_blockers=evidence_blockers,
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


def _operator_snapshot(admission_snapshot: SleeveAdmissionSnapshot | None = None) -> OperatorSnapshot:
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
        sleeve_promotion_review=None,
        sleeve_admission=admission_snapshot,
        escalation_review=None,
    )


@dataclass(frozen=True)
class _ReviewSnapshot:
    updated_at_ns: int = 303
    provisional_verdict: str = "promote"
    provisional_summary: str = "Promotion review supports candidate."
    campaign_ids: tuple[str, ...] = ("campaign-1",)
    campaign_count: int = 1
    ext_regime_quality: str = "supportive"
    ext_regime_governance: dict = field(default_factory=dict)
    verdict_distribution: dict = field(default_factory=dict)
    execution_sufficiency: dict = field(default_factory=dict)
    symbol_breadth: dict = field(default_factory=dict)


class _ReviewStatus:
    value = "active"


class _Review:
    campaign_count = 1
    final_report = None
    review_id = "review-19d"
    status = _ReviewStatus()

    def current_snapshot(self) -> _ReviewSnapshot:
        return _ReviewSnapshot()

    def get_promotion_reason_summary(self) -> dict:
        return {
            "pass_reasons": ("promotion_review_supported",),
            "warning_reasons": (),
            "fail_reasons": (),
            "insufficient_reasons": (),
            "pass_count": 1,
            "warning_count": 0,
            "fail_count": 0,
            "insufficient_count": 0,
        }

    def get_missing_evidence(self) -> dict:
        return {
            "insufficient_criteria": [],
            "warning_criteria": [],
            "fail_criteria": [],
            "message": "Review evidence sufficient.",
        }


def _orchestrator(admission_snapshot: SleeveAdmissionSnapshot | None = None) -> ServiceOrchestrator:
    orch = ServiceOrchestrator(service=MagicMock(), readiness_level="paper_live")
    orch.operator_snapshot = MagicMock(return_value=_operator_snapshot(admission_snapshot))  # type: ignore[method-assign]
    orch._decision_pack_readiness_status = MagicMock(return_value=None)  # type: ignore[method-assign]
    orch._review = _Review()  # type: ignore[assignment]
    return orch


def test_decision_pack_includes_sleeve_admission_evidence_blockers_when_stage4_blocker_exists():
    pack = _orchestrator(_admission_snapshot()).decision_pack()

    assert pack.sleeve_admission_evidence_blockers == (_STAGE4_BLOCKER,)
    assert pack.insufficient_evidence == ()


def test_decision_pack_dict_includes_stage4_blocker_json_safe():
    pack = _orchestrator(_admission_snapshot()).decision_pack()

    payload = decision_pack_to_dict(pack)
    assert payload["sleeve_admission_evidence_blockers"] == [_STAGE4_BLOCKER]
    assert json.dumps(payload)

    missing = decision_pack_missing_evidence(pack)
    assert missing["sleeve_admission_evidence_blockers"] == [_STAGE4_BLOCKER]
    assert missing["details"]["sleeve_admission_evidence_blockers"] == [_STAGE4_BLOCKER]


def test_decision_pack_export_load_roundtrip_preserves_sleeve_evidence(tmp_path):
    store = EvidenceStore(evidence_dir=tmp_path / "evidence", config=EvidenceStoreConfig())
    pack = _orchestrator(_admission_snapshot()).decision_pack()

    result = export_operator_decision_pack(pack=pack, evidence_store=store)
    assert result.success is True

    loaded = load_operator_decision_pack(evidence_store=store)
    assert loaded.sleeve_admission_evidence_blockers == (_STAGE4_BLOCKER,)
    assert loaded.sleeve_pbo_allocation_caps == ((_SLEEVE_ID, 0.5),)


def test_old_decision_pack_payload_without_sleeve_fields_loads_safely():
    payload = decision_pack_to_dict(_orchestrator(_admission_snapshot()).decision_pack())
    del payload["sleeve_admission_evidence_blockers"]
    del payload["sleeve_pbo_allocation_caps"]

    loaded = decision_pack_from_dict(payload)

    assert loaded.sleeve_admission_evidence_blockers == ()
    assert loaded.sleeve_pbo_allocation_caps == ()


def test_combined_status_dict_behavior_remains_unchanged_for_stage4_blocker():
    payload = _orchestrator(_admission_snapshot()).combined_status_dict()

    assert payload["sleeve_admission"]["portfolio_summary"]["evidence_blockers"] == [_STAGE4_BLOCKER]
    assert payload["sleeve_admission"]["admission_results"][0]["pbo_allocation_cap"] == 0.5


def test_decision_pack_preserves_sleeve_pbo_allocation_cap_metadata():
    pack = _orchestrator(_admission_snapshot()).decision_pack()

    assert pack.sleeve_pbo_allocation_caps == ((_SLEEVE_ID, 0.5),)
    assert decision_pack_to_dict(pack)["sleeve_pbo_allocation_caps"] == [[_SLEEVE_ID, 0.5]]
    assert decision_pack_missing_evidence(pack)["sleeve_pbo_allocation_caps"] == [[_SLEEVE_ID, 0.5]]


def test_sleeve_evidence_metadata_does_not_change_escalation_verdict():
    orch = _orchestrator(_admission_snapshot())
    with_sleeve_metadata = orch.decision_pack()
    without_sleeve_metadata = replace(
        with_sleeve_metadata,
        sleeve_admission_evidence_blockers=(),
        sleeve_pbo_allocation_caps=(),
    )

    with_decision = orch._build_escalation_decision(with_sleeve_metadata)
    without_decision = orch._build_escalation_decision(without_sleeve_metadata)

    assert with_sleeve_metadata.operator_disposition == "promotable"
    assert with_sleeve_metadata.insufficient_evidence == ()
    assert with_decision.escalation_stage == without_decision.escalation_stage == EscalationStage.PAPER_ONLY
