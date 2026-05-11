from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from unittest.mock import MagicMock

import crypto_core.service.sleeve_portfolio as portfolio
import crypto_core.validation as validation
from crypto_core.edge.models import EdgeFamily, EdgeSignal, SignalDirection
from crypto_core.execution.engine import ExecutionConfig, ExecutionEngine
from crypto_core.execution.models import ExecutionMode, ExecutionRequest, OrderIntent, RejectionReason
from crypto_core.guard.models import NoTradeDecision
from crypto_core.risk.models import RiskDecision, RiskEvaluation
from crypto_core.service.artifact_export import decision_pack_to_dict
from crypto_core.service.service_orchestrator import (
    EvidenceSufficiencyState,
    OperatorSnapshot,
    ServiceOrchestrator,
)
from crypto_core.service.sleeve_admission_controller import SleeveAdmissionController, SleeveAdmissionVerdict
from crypto_core.service.sleeve_candidate_workflow import (
    SleeveCandidateWorkflowController,
    SleeveCandidateWorkflowStatus,
)
from crypto_core.service.sleeve_promotion_review_controller import SleevePromotionReviewController
from crypto_core.state.models import SystemState

_DAY_NS = 86_400 * 1_000_000_000
_EDGE_ID = "edge-20a"
_SLEEVE_ID = "sleeve-stage5"
_STAGE5_MISSING = portfolio.STAGE5_LIVE_READINESS_GATE_MISSING


def _pipeline_ready() -> validation.ValidationPipelineResult:
    stage = validation.ValidationPipelineStageStatus(
        stage="stage",
        ran=True,
        passed=True,
        skipped=False,
        rejection_reasons=(),
    )
    return validation.ValidationPipelineResult(
        validation_ready=True,
        stage2_status=replace(stage, stage="stage2_walk_forward"),
        pbo_status=replace(stage, stage="pbo"),
        stage3_status=replace(stage, stage="stage3_stress"),
        pbo_allocation_cap=None,
        rejection_reasons=(),
        missing_stages=(),
    )


def _baseline() -> validation.Stage4BacktestBaseline:
    return validation.Stage4BacktestBaseline(
        baseline_id="baseline-20a",
        edge_id=_EDGE_ID,
        as_of_ns=31 * _DAY_NS,
        backtest_sharpe=2.0,
        backtest_hit_rate=0.60,
        backtest_slippage_bps=4.0,
        backtest_fill_rate=0.98,
        source_window_ids=("wf-001", "wf-002"),
    )


def _paper_summary() -> validation.Stage4PaperSummary:
    return validation.Stage4PaperSummary(
        paper_id="paper-20a",
        edge_id=_EDGE_ID,
        started_at_ns=1,
        stopped_at_ns=31 * _DAY_NS + 1,
        paper_sharpe=1.2,
        paper_hit_rate=0.58,
        paper_slippage_bps=4.5,
        paper_fill_rate=0.97,
        paper_trade_count=42,
    )


def _stage4_pass() -> validation.Stage4ComparisonResult:
    return validation.compare_stage4(_baseline(), _paper_summary())


def _stage5_gate(**overrides: object) -> portfolio.Stage5LiveReadinessGate:
    values = {
        "edge_id": _EDGE_ID,
        "allocation_tier_pct": 10.0,
        "weeks_at_tier": 0,
        "as_of_ns": 100,
        "stage4_passed": True,
        "operator_approval_recorded": True,
        "live_api_credentials_valid": True,
        "kill_switch_clear": True,
        "risk_governance_clear": True,
    }
    values.update(overrides)
    return portfolio.build_stage5_live_readiness_gate(**values)  # type: ignore[arg-type]


def _base_sleeve(
    *,
    stage4_result: validation.Stage4ComparisonResult | None = None,
    stage5_gate: portfolio.Stage5LiveReadinessGate | None = None,
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
            ("campaign-20a",),
        ),
        promotion_support=portfolio.SleevePromotionSupportResult(
            portfolio.SleevePromotionSupportStatus.SUPPORTIVE,
            True,
            portfolio.SleeveCampaignEvidenceStatus.CAMPAIGN_SUPPORTED,
            portfolio.SleeveQualificationStatus.PAPER_QUALIFIED,
            portfolio.SleeveRecommendationStatus.RECOMMENDED_ACTIVE,
        ),
        validation_pipeline_result=_pipeline_ready(),
        stage4_comparison_result=stage4_result,
        stage4_backtest_baseline=_baseline(),
        stage5_entry_gate=stage5_gate,
    )


def _portfolio_snapshot(sleeve: portfolio.CryptoSleeveState) -> portfolio.SleevePortfolioSnapshot:
    return portfolio.build_sleeve_portfolio_snapshot(
        sleeves=(sleeve,),
        as_of_ns=200,
        readiness_level="paper_live",
        readiness_is_supportive=True,
    )


def _admission_verdict(sleeve: portfolio.CryptoSleeveState) -> SleeveAdmissionVerdict:
    candidate = portfolio._build_sleeve_promotion_candidate_result(sleeve)
    snapshot = portfolio.SleevePortfolioSnapshot(
        as_of_ns=200,
        sleeves=(replace(sleeve, promotion_candidate=candidate),),
    )
    workflow = SleeveCandidateWorkflowController(
        workflow_id="workflow-20a",
        created_at_ns=1,
        updated_at_ns=1,
        status=SleeveCandidateWorkflowStatus.CREATED,
    )
    workflow.start(workflow_id="workflow-20a", started_at_ns=2)
    workflow_snapshot = workflow.inspect(snapshot)
    review_controller = SleevePromotionReviewController(workflow_snapshot)
    review_result = review_controller.build_review_results()[0]
    review_summary = review_controller.build_portfolio_summary((review_result,))
    return SleeveAdmissionController(review_summary).build_admission_results()[0].verdict


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


def _operator_snapshot(sleeve: portfolio.CryptoSleeveState) -> OperatorSnapshot:
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
        sleeve_portfolio=_portfolio_snapshot(sleeve),
    )


@dataclass(frozen=True)
class _ReviewSnapshot:
    updated_at_ns: int = 303
    provisional_verdict: str = "promote"
    provisional_summary: str = "Promotion review supports candidate."
    campaign_ids: tuple[str, ...] = ("campaign-20a",)
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
    review_id = "review-20a"
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


def _orchestrator(sleeve: portfolio.CryptoSleeveState) -> ServiceOrchestrator:
    orchestrator = ServiceOrchestrator(service=MagicMock(), readiness_level="paper_live")
    orchestrator.operator_snapshot = MagicMock(return_value=_operator_snapshot(sleeve))  # type: ignore[method-assign]
    orchestrator._decision_pack_readiness_status = MagicMock(return_value=None)  # type: ignore[method-assign]
    orchestrator._review = _Review()  # type: ignore[assignment]
    return orchestrator


def _edge_signal() -> EdgeSignal:
    return EdgeSignal(
        family=EdgeFamily.ORDER_FLOW_IMBALANCE,
        symbol="BTCUSDT",
        exchange="binance",
        direction=SignalDirection.BUY,
        confidence=0.5,
        score=0.5,
        evidence={"ofi": 0.5},
        timestamp_ns=100,
        is_valid=True,
        block_reason=None,
    )


def _execution_request() -> ExecutionRequest:
    return ExecutionRequest(
        symbol="BTCUSDT",
        exchange="binance",
        intent=OrderIntent.BUY,
        size=0.01,
        price_hint=50_000.0,
        risk_evaluation=RiskEvaluation(
            decision=RiskDecision.APPROVED,
            block_reason=None,
            system_state=SystemState.NORMAL,
            edge_signal=_edge_signal(),
            no_trade_decision=NoTradeDecision.allow(),
            evidence={},
            timestamp_ns=100,
        ),
        timestamp_ns=100,
    )


def test_missing_stage5_gate_is_not_live_ready():
    sleeve = _portfolio_snapshot(_base_sleeve(stage4_result=_stage4_pass())).sleeves[0]

    assert sleeve.promotion_candidate.stage5_live_ready is False
    assert sleeve.promotion_candidate.stage5_live_readiness_blockers == (_STAGE5_MISSING,)


def test_stage4_pass_alone_is_not_live_ready():
    sleeve = _base_sleeve(stage4_result=_stage4_pass())

    pack = _orchestrator(sleeve).decision_pack()

    assert pack.stage5_live_ready is False
    assert pack.stage5_live_readiness_blockers == (_STAGE5_MISSING,)


def test_admitted_active_alone_is_not_live_ready():
    sleeve = _base_sleeve(stage4_result=_stage4_pass())

    assert _admission_verdict(sleeve) == SleeveAdmissionVerdict.ADMITTED_ACTIVE
    assert _orchestrator(sleeve).decision_pack().stage5_live_ready is False


def test_stage5_gate_with_failed_operator_approval_blocks():
    gate = _stage5_gate(operator_approval_recorded=False)

    assert gate.passed is False
    assert portfolio.stage5_live_readiness_blockers(gate) == ("stage5:operator_approval_missing",)


def test_stage5_gate_with_failed_credentials_flag_blocks_without_reading_credentials(monkeypatch):
    monkeypatch.setenv("CRYPTO_LIVE_API_KEY", "must-not-be-read")

    gate = _stage5_gate(live_api_credentials_valid=False)

    assert gate.passed is False
    assert portfolio.stage5_live_readiness_blockers(gate) == ("stage5:live_api_credentials_not_verified",)


def test_stage5_gate_with_kill_switch_and_risk_blockers_blocks():
    gate = _stage5_gate(kill_switch_clear=False, risk_governance_clear=False)

    assert portfolio.stage5_live_readiness_blockers(gate) == (
        "stage5:kill_switch_not_clear",
        "stage5:risk_governance_not_clear",
    )


def test_valid_stage5_gate_serializes_deserializes():
    gate = _stage5_gate()
    payload = portfolio.stage5_live_readiness_gate_to_dict(gate)
    restored = portfolio.stage5_live_readiness_gate_from_dict(payload)

    assert json.dumps(payload)
    assert payload["rejection_reasons"] == []
    assert restored == gate
    assert portfolio.stage5_live_ready(restored) is True


def test_old_sleeve_payload_without_stage5_gate_loads_none():
    payload = portfolio.crypto_sleeve_state_to_dict(
        _base_sleeve(stage4_result=_stage4_pass(), stage5_gate=_stage5_gate())
    )
    del payload["stage5_entry_gate"]

    restored = portfolio.crypto_sleeve_state_from_dict(payload)

    assert restored.stage5_entry_gate is None


def test_decision_pack_and_combined_status_expose_stage5_blockers_json_safe():
    sleeve = _base_sleeve(stage4_result=_stage4_pass())
    orchestrator = _orchestrator(sleeve)

    pack_payload = decision_pack_to_dict(orchestrator.decision_pack())
    status_payload = orchestrator.combined_status_dict()

    assert pack_payload["stage5_live_readiness_blockers"] == [_STAGE5_MISSING]
    assert status_payload["sleeve_portfolio"]["sleeves"][0]["promotion_candidate"][
        "stage5_live_readiness_blockers"
    ] == [_STAGE5_MISSING]
    assert json.dumps(pack_payload)
    assert json.dumps(status_payload)


def test_stage5_metadata_does_not_change_escalation_verdict_behavior():
    orchestrator = _orchestrator(_base_sleeve(stage4_result=_stage4_pass()))
    pack = orchestrator.decision_pack()
    with_stage5_metadata = replace(
        pack,
        stage5_live_ready=True,
        stage5_live_ready_sleeve_ids=(_SLEEVE_ID,),
        stage5_live_readiness_blockers=(),
    )

    assert (
        orchestrator._build_escalation_decision(pack).escalation_stage
        == orchestrator._build_escalation_decision(with_stage5_metadata).escalation_stage
    )


def test_live_execution_mode_remains_fail_closed_without_clients():
    decision = ExecutionEngine(ExecutionConfig(mode=ExecutionMode.LIVE)).execute(_execution_request())

    assert decision.allowed is False
    assert decision.rejection_reason == RejectionReason.LIVE_NOT_ENABLED


def test_repeated_same_input_gives_deterministic_stage5_output():
    def payload() -> dict:
        return decision_pack_to_dict(_orchestrator(_base_sleeve(stage4_result=_stage4_pass())).decision_pack())

    assert payload() == payload()
