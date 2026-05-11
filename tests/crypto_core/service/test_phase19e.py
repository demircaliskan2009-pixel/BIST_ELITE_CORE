from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from unittest.mock import MagicMock

import crypto_core.service.sleeve_portfolio as portfolio
import crypto_core.validation as validation
from crypto_core.service.artifact_export import (
    decision_pack_from_dict,
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
    SleeveAdmissionController,
    SleeveAdmissionSnapshot,
    SleeveAdmissionVerdict,
)
from crypto_core.service.sleeve_candidate_workflow import (
    SleeveCandidateWorkflowController,
    SleeveCandidateWorkflowSnapshot,
    SleeveCandidateWorkflowStatus,
)
from crypto_core.service.sleeve_promotion_review_controller import (
    SleevePromotionReviewController,
    SleevePromotionReviewSnapshot,
)

_DAY_NS = 86_400 * 1_000_000_000
_SLEEVE_ID = "sleeve-microstructure"
_STAGE4_MISSING = "stage4:comparison_missing"
_STAGE4_REJECT = "stage4:paper_sharpe_below_backtest_threshold"
_STAGE4_INSUFFICIENT = "stage4:paper_summary_missing"
_VALIDATION_REJECT = "stage2:stage2_missing"


@dataclass(frozen=True)
class _Chain:
    candidate: portfolio.SleevePromotionCandidateResult
    workflow_snapshot: SleeveCandidateWorkflowSnapshot
    review_controller: SleevePromotionReviewController
    review_snapshot: SleevePromotionReviewSnapshot
    admission_snapshot: SleeveAdmissionSnapshot

    @property
    def admission_result(self):
        return self.admission_snapshot.admission_results[0]


def _pipeline(
    *,
    ready: bool,
    reasons: tuple[str, ...] = (),
    cap: float | None = 0.5,
) -> validation.ValidationPipelineResult:
    stage = validation.ValidationPipelineStageStatus(
        stage="stage",
        ran=True,
        passed=ready,
        skipped=False,
        rejection_reasons=(),
    )
    return validation.ValidationPipelineResult(
        validation_ready=ready,
        stage2_status=replace(stage, stage="stage2_walk_forward"),
        pbo_status=replace(stage, stage="pbo"),
        stage3_status=replace(stage, stage="stage3_stress"),
        pbo_allocation_cap=cap,
        rejection_reasons=reasons,
        missing_stages=() if ready else ("stage2_walk_forward",),
    )


def _baseline(*, backtest_sharpe: float = 2.0) -> validation.Stage4BacktestBaseline:
    return validation.Stage4BacktestBaseline(
        baseline_id="baseline-19e",
        edge_id="edge-19e",
        as_of_ns=31 * _DAY_NS,
        backtest_sharpe=backtest_sharpe,
        backtest_hit_rate=0.60,
        backtest_slippage_bps=4.0,
        backtest_fill_rate=0.98,
        source_window_ids=("wf-001", "wf-002"),
    )


def _paper_summary(*, paper_sharpe: float | None = 1.2) -> validation.Stage4PaperSummary:
    return validation.Stage4PaperSummary(
        paper_id="paper-19e",
        edge_id="edge-19e",
        started_at_ns=1,
        stopped_at_ns=31 * _DAY_NS + 1,
        paper_sharpe=paper_sharpe,
        paper_hit_rate=0.58,
        paper_slippage_bps=4.5,
        paper_fill_rate=0.97,
        paper_trade_count=42,
    )


def _stage4_pass() -> validation.Stage4ComparisonResult:
    return validation.compare_stage4(_baseline(), _paper_summary())


def _stage4_reject() -> validation.Stage4ComparisonResult:
    return validation.compare_stage4(_baseline(), _paper_summary(paper_sharpe=0.5))


def _stage4_insufficient() -> validation.Stage4ComparisonResult:
    return validation.compare_stage4(_baseline(), None)


def _base_sleeve(
    *,
    validation_result: validation.ValidationPipelineResult | None,
    stage4_result: validation.Stage4ComparisonResult | None,
    required: bool = False,
) -> portfolio.CryptoSleeveState:
    return portfolio.CryptoSleeveState(
        sleeve_id=_SLEEVE_ID,
        sleeve_type=portfolio.CryptoSleeveType.MICROSTRUCTURE,
        status=portfolio.CryptoSleeveStatus.DEFINED,
        qualification=portfolio.SleeveQualificationResult(
            portfolio.SleeveQualificationStatus.PAPER_QUALIFIED,
            True,
        ),
        recommendation=portfolio.SleeveRecommendationResult(
            portfolio.SleeveRecommendationStatus.RECOMMENDED_ACTIVE,
            True,
            True,
            portfolio.SleeveQualificationStatus.PAPER_QUALIFIED,
        ),
        campaign_evidence=portfolio.SleeveCampaignEvidenceResult(
            portfolio.SleeveCampaignEvidenceStatus.CAMPAIGN_SUPPORTED,
            True,
            True,
            True,
            ("campaign-1",),
        ),
        promotion_support=portfolio.SleevePromotionSupportResult(
            portfolio.SleevePromotionSupportStatus.SUPPORTIVE,
            True,
            portfolio.SleeveCampaignEvidenceStatus.CAMPAIGN_SUPPORTED,
            portfolio.SleeveQualificationStatus.PAPER_QUALIFIED,
            portfolio.SleeveRecommendationStatus.RECOMMENDED_ACTIVE,
        ),
        validation_pipeline_result=validation_result,
        stage4_comparison_result=stage4_result,
        stage4_comparison_required=required,
        stage4_backtest_baseline=_baseline(),
    )


def _chain(
    *,
    validation_result: validation.ValidationPipelineResult | None,
    stage4_result: validation.Stage4ComparisonResult | None,
    required: bool = False,
) -> _Chain:
    base = _base_sleeve(
        validation_result=validation_result,
        stage4_result=stage4_result,
        required=required,
    )
    candidate = portfolio._build_sleeve_promotion_candidate_result(base)
    sleeve = replace(base, promotion_candidate=candidate)
    workflow = SleeveCandidateWorkflowController(
        workflow_id="workflow-19e",
        created_at_ns=1,
        updated_at_ns=1,
        status=SleeveCandidateWorkflowStatus.CREATED,
    )
    workflow.start(workflow_id="workflow-19e", started_at_ns=2)
    workflow_snapshot = workflow.inspect(portfolio.SleevePortfolioSnapshot(as_of_ns=3, sleeves=(sleeve,)))
    review_controller = SleevePromotionReviewController(workflow_snapshot)
    review_result = review_controller.build_review_results()[0]
    review_summary = review_controller.build_portfolio_summary((review_result,))
    review_snapshot = review_controller.snapshot()
    admission_snapshot = SleeveAdmissionController(review_summary).snapshot()
    return _Chain(
        candidate=candidate,
        workflow_snapshot=workflow_snapshot,
        review_controller=review_controller,
        review_snapshot=review_snapshot,
        admission_snapshot=admission_snapshot,
    )


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


def _operator_snapshot(chain: _Chain) -> OperatorSnapshot:
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
        sleeve_promotion_review=chain.review_snapshot,
        sleeve_admission=chain.admission_snapshot,
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
    review_id = "review-19e"
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


def _orchestrator(chain: _Chain) -> ServiceOrchestrator:
    orchestrator = ServiceOrchestrator(service=MagicMock(), readiness_level="paper_live")
    orchestrator.operator_snapshot = MagicMock(return_value=_operator_snapshot(chain))  # type: ignore[method-assign]
    orchestrator._decision_pack_readiness_status = MagicMock(return_value=None)  # type: ignore[method-assign]
    orchestrator._review = _Review()  # type: ignore[assignment]
    return orchestrator


def _decision_pack(chain: _Chain):
    return _orchestrator(chain).decision_pack()


def test_validation_ready_true_without_stage4_result_blocks_admission_and_decision_pack():
    chain = _chain(validation_result=_pipeline(ready=True), stage4_result=None)
    pack = _decision_pack(chain)

    assert chain.admission_result.verdict == SleeveAdmissionVerdict.ADMITTED_UNALLOCATED
    assert _STAGE4_MISSING in chain.admission_result.evidence_blockers
    assert _STAGE4_MISSING in pack.sleeve_admission_evidence_blockers
    assert _STAGE4_MISSING in decision_pack_to_dict(pack)["sleeve_admission_evidence_blockers"]


def test_stage4_reject_blocks_admission_and_decision_pack_reason():
    chain = _chain(validation_result=_pipeline(ready=True), stage4_result=_stage4_reject())
    pack = _decision_pack(chain)

    assert chain.admission_result.verdict == SleeveAdmissionVerdict.ADMITTED_UNALLOCATED
    assert _STAGE4_REJECT in chain.admission_result.evidence_blockers
    assert _STAGE4_REJECT in pack.sleeve_admission_evidence_blockers


def test_stage4_insufficient_evidence_blocks_admission_and_decision_pack_reason():
    chain = _chain(validation_result=_pipeline(ready=True), stage4_result=_stage4_insufficient())
    pack = _decision_pack(chain)

    assert chain.admission_result.verdict == SleeveAdmissionVerdict.ADMITTED_UNALLOCATED
    assert _STAGE4_INSUFFICIENT in chain.admission_result.evidence_blockers
    assert _STAGE4_INSUFFICIENT in pack.sleeve_admission_evidence_blockers


def test_stage4_pass_with_no_other_blockers_can_admit_active():
    chain = _chain(validation_result=_pipeline(ready=True), stage4_result=_stage4_pass())
    pack = _decision_pack(chain)

    assert chain.candidate.missing_evidence == ()
    assert chain.admission_result.verdict == SleeveAdmissionVerdict.ADMITTED_ACTIVE
    assert pack.sleeve_admission_evidence_blockers == ()


def test_validation_blocker_and_stage4_blocker_survive_in_deterministic_order():
    chain = _chain(
        validation_result=_pipeline(ready=False, reasons=(_VALIDATION_REJECT,)),
        stage4_result=_stage4_reject(),
        required=True,
    )
    evidence = chain.admission_result.evidence_blockers
    pack = _decision_pack(chain)

    assert _VALIDATION_REJECT in evidence
    assert _STAGE4_REJECT in evidence
    assert evidence.index(_VALIDATION_REJECT) < evidence.index(_STAGE4_REJECT)
    assert pack.sleeve_admission_evidence_blockers == (_VALIDATION_REJECT, _STAGE4_REJECT)


def test_crypto_sleeve_state_roundtrip_preserves_stage4_baseline_comparison_required():
    sleeve = _base_sleeve(
        validation_result=_pipeline(ready=True),
        stage4_result=_stage4_pass(),
    )

    restored = portfolio.crypto_sleeve_state_from_dict(portfolio.crypto_sleeve_state_to_dict(sleeve))

    assert restored.stage4_comparison_required is True
    assert restored.stage4_backtest_baseline.baseline_id == "baseline-19e"
    assert restored.stage4_comparison_result.status == validation.Stage4ComparisonStatus.PASS.value
    assert restored.stage4_comparison_result.passed is True


def test_operator_snapshot_combined_status_dict_is_json_safe_with_blockers():
    chain = _chain(validation_result=_pipeline(ready=True), stage4_result=_stage4_reject())

    payload = _orchestrator(chain).combined_status_dict()

    assert json.dumps(payload)
    assert payload["sleeve_admission"]["admission_results"][0]["verdict"] == "admitted_unallocated"
    assert _STAGE4_REJECT in payload["sleeve_admission"]["portfolio_summary"]["evidence_blockers"]


def test_decision_pack_export_load_preserves_blockers_and_pbo_caps(tmp_path):
    chain = _chain(validation_result=_pipeline(ready=True, cap=0.5), stage4_result=_stage4_reject())
    pack = _decision_pack(chain)
    store = EvidenceStore(evidence_dir=tmp_path / "evidence", config=EvidenceStoreConfig())

    result = export_operator_decision_pack(pack=pack, evidence_store=store)
    assert result.success is True
    loaded = load_operator_decision_pack(evidence_store=store)

    assert _STAGE4_REJECT in loaded.sleeve_admission_evidence_blockers
    assert loaded.sleeve_pbo_allocation_caps == ((_SLEEVE_ID, 0.5),)


def test_old_decision_pack_payload_without_sleeve_fields_remains_compatible():
    payload = decision_pack_to_dict(_decision_pack(_chain(validation_result=_pipeline(ready=True), stage4_result=None)))
    del payload["sleeve_admission_evidence_blockers"]
    del payload["sleeve_pbo_allocation_caps"]

    loaded = decision_pack_from_dict(payload)

    assert loaded.sleeve_admission_evidence_blockers == ()
    assert loaded.sleeve_pbo_allocation_caps == ()


def test_repeated_same_input_gives_deterministic_decision_pack_dict():
    def build_payload() -> dict:
        chain = _chain(validation_result=_pipeline(ready=True), stage4_result=_stage4_reject())
        return decision_pack_to_dict(_decision_pack(chain))

    assert build_payload() == build_payload()


def test_sleeve_promotion_review_dict_surfaces_are_json_safe():
    chain = _chain(validation_result=_pipeline(ready=True), stage4_result=_stage4_reject())

    controller_payload = chain.review_controller.to_dict()
    orchestrator = ServiceOrchestrator(service=MagicMock(), readiness_level="paper_live")
    orchestrator._sleeve_promotion_review_controller = chain.review_controller
    orchestrator_payload = orchestrator.sleeve_promotion_review_dict()

    assert json.dumps(controller_payload)
    assert json.dumps(orchestrator_payload)
    assert controller_payload["review_results"][0]["verdict"] == "review_supported"
    assert _STAGE4_REJECT in orchestrator_payload["review_results"][0]["missing_evidence"]
