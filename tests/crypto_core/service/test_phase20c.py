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
from crypto_core.service.models import (
    ExecutionIntelligenceStatus,
    QueuePressure,
    QueueSnapshot,
    ServiceStatus,
    WatchdogStatus,
)
from crypto_core.service.service_orchestrator import ServiceOrchestrator
from crypto_core.state.models import SystemState

_DAY_NS = 86_400 * 1_000_000_000
_EDGE_ID = "edge-20c"
_SLEEVE_ID = "sleeve-stage5-evidence"


class _Service:
    def status(self) -> ServiceStatus:
        return ServiceStatus(
            service_mode="running",
            runtime_status=None,
            queue=QueueSnapshot(
                current_depth=0,
                max_size=100,
                pressure=QueuePressure.NORMAL,
                total_enqueued=10,
                total_dropped=0,
                total_processed=10,
            ),
            watchdog=WatchdogStatus(
                consumer_alive=True,
                last_event_time_ns=31 * _DAY_NS,
                last_cycle_time_ns=31 * _DAY_NS,
                seconds_since_event=0.0,
                seconds_since_cycle=0.0,
                stall_detected=False,
                stall_threshold_s=60.0,
            ),
            symbol_health=(),
            symbol_count=0,
            trading_enabled=True,
            blocked_reason=None,
            last_error=None,
            execution_intelligence=ExecutionIntelligenceStatus(
                mode="optional",
                route_binding_enabled=True,
                tca_loop_enabled=True,
                tca_store_available=True,
                replay_dedup_bootstrapped=True,
                degraded=False,
                degraded_reasons=(),
            ),
        )


@dataclass(frozen=True)
class _ReviewSnapshot:
    updated_at_ns: int = 303
    provisional_verdict: str = "promote"
    provisional_summary: str = "Promotion review supports candidate."
    insufficient_evidence: tuple[str, ...] = ()
    is_ready_to_finalize: bool = True
    campaign_ids: tuple[str, ...] = ("campaign-20c",)
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
    is_finalized = False
    review_id = "review-20c"
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
        baseline_id="baseline-20c",
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
        paper_id="paper-20c",
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


def _evidence(**overrides: object) -> portfolio.Stage5RuntimeEvidenceBundle:
    values = {
        "edge_id": _EDGE_ID,
        "as_of_ns": 100,
        "operator_approval": portfolio.Stage5OperatorApprovalEvidence(
            approved=True,
            approver_id="ops-lead",
            approved_at_ns=90,
            approval_reference="approval-ticket-20c",
            rejection_reasons=(),
        ),
        "credential_attestation": portfolio.Stage5CredentialAttestationEvidence(
            live_api_credentials_valid=True,
            attested_by="security-lead",
            attested_at_ns=91,
            attestation_reference="credential-attestation-20c",
            rejection_reasons=(),
        ),
        "risk_governance": portfolio.Stage5RiskGovernanceEvidence(
            risk_governance_clear=True,
            kill_switch_clear=True,
            ehs_at_entry=0.75,
            max_drawdown_bps=None,
            attested_at_ns=92,
            rejection_reasons=(),
        ),
        "canary_tier": portfolio.Stage5CanaryTierEvidence(
            allocation_tier_pct=10.0,
            weeks_at_tier=0,
            canary_observation_count=12,
            canary_pnl_non_negative=True,
            canary_drawdown_within_limit=True,
            canary_slippage_within_limit=True,
            canary_incidents=0,
            as_of_ns=100,
            rejection_reasons=(),
        ),
        "rejection_reasons": (),
    }
    values.update(overrides)
    return portfolio.Stage5RuntimeEvidenceBundle(**values)  # type: ignore[arg-type]


def _sleeve() -> portfolio.CryptoSleeveState:
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
            ("campaign-20c",),
        ),
        promotion_support=portfolio.SleevePromotionSupportResult(
            portfolio.SleevePromotionSupportStatus.SUPPORTIVE,
            True,
            portfolio.SleeveCampaignEvidenceStatus.CAMPAIGN_SUPPORTED,
            portfolio.SleeveQualificationStatus.PAPER_QUALIFIED,
            portfolio.SleeveRecommendationStatus.RECOMMENDED_ACTIVE,
        ),
        validation_pipeline_result=_pipeline_ready(),
        stage4_backtest_baseline=_baseline(),
        stage4_comparison_result=_stage4_pass(),
    )


def _orchestrator() -> ServiceOrchestrator:
    orchestrator = ServiceOrchestrator(
        service=_Service(),
        readiness_level="paper_live",
        sleeves=(_sleeve(),),
    )
    orchestrator._decision_pack_readiness_status = MagicMock(return_value=None)  # type: ignore[method-assign]
    orchestrator._review = _Review()  # type: ignore[assignment]
    return orchestrator


def _build_gate(evidence: portfolio.Stage5RuntimeEvidenceBundle) -> portfolio.Stage5LiveReadinessGate:
    return portfolio.build_stage5_live_readiness_gate_from_evidence(evidence)


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


def test_full_valid_evidence_bundle_builds_passing_stage5_gate():
    gate = _build_gate(_evidence())

    assert gate.passed is True
    assert gate.edge_id == _EDGE_ID
    assert gate.rejection_reasons == ()
    assert portfolio.stage5_live_ready(gate) is True


def test_missing_operator_approval_builds_failed_gate_with_stable_reason():
    evidence = _evidence(
        operator_approval=replace(_evidence().operator_approval, approved=False),
    )

    gate = _build_gate(evidence)

    assert gate.passed is False
    assert gate.rejection_reasons == ("stage5:operator_approval_missing",)


def test_missing_credential_attestation_blocks_without_reading_env(monkeypatch):
    monkeypatch.setenv("CRYPTO_LIVE_API_KEY", "must-not-be-read")
    evidence = _evidence(
        credential_attestation=replace(
            _evidence().credential_attestation,
            live_api_credentials_valid=False,
        ),
    )

    gate = _build_gate(evidence)

    assert gate.passed is False
    assert gate.rejection_reasons == ("stage5:live_api_credentials_not_verified",)


def test_kill_switch_not_clear_blocks():
    gate = _build_gate(_evidence(risk_governance=replace(_evidence().risk_governance, kill_switch_clear=False)))

    assert gate.rejection_reasons == ("stage5:kill_switch_not_clear",)


def test_risk_governance_not_clear_blocks():
    gate = _build_gate(_evidence(risk_governance=replace(_evidence().risk_governance, risk_governance_clear=False)))

    assert gate.rejection_reasons == ("stage5:risk_governance_not_clear",)


def test_canary_negative_pnl_blocks():
    gate = _build_gate(_evidence(canary_tier=replace(_evidence().canary_tier, canary_pnl_non_negative=False)))

    assert gate.rejection_reasons == ("stage5:canary_pnl_negative",)


def test_canary_drawdown_out_of_limit_blocks():
    gate = _build_gate(_evidence(canary_tier=replace(_evidence().canary_tier, canary_drawdown_within_limit=False)))

    assert gate.rejection_reasons == ("stage5:canary_drawdown_out_of_limit",)


def test_canary_slippage_out_of_limit_blocks():
    gate = _build_gate(_evidence(canary_tier=replace(_evidence().canary_tier, canary_slippage_within_limit=False)))

    assert gate.rejection_reasons == ("stage5:canary_slippage_out_of_limit",)


def test_canary_incidents_block():
    gate = _build_gate(_evidence(canary_tier=replace(_evidence().canary_tier, canary_incidents=1)))

    assert gate.rejection_reasons == ("stage5:canary_incidents_present",)


def test_invalid_tier_pct_blocks():
    gate = _build_gate(_evidence(canary_tier=replace(_evidence().canary_tier, allocation_tier_pct=12.5)))

    assert gate.rejection_reasons == ("stage5:allocation_tier_invalid",)


def test_insufficient_weeks_at_tier_blocks_using_prd_stage5_timeline():
    gate = _build_gate(
        _evidence(
            canary_tier=replace(
                _evidence().canary_tier,
                allocation_tier_pct=25.0,
                weeks_at_tier=1,
            )
        )
    )

    assert portfolio.STAGE5_REQUIRED_WEEKS_BY_TIER_PCT[25.0] == 2
    assert gate.rejection_reasons == ("stage5:weeks_at_tier_below_minimum",)


def test_ehs_below_minimum_blocks_live_entry():
    gate = _build_gate(_evidence(risk_governance=replace(_evidence().risk_governance, ehs_at_entry=0.49)))

    assert gate.rejection_reasons == ("stage5:ehs_below_live_entry_minimum",)


def test_evidence_bundle_dict_roundtrip_preserves_nested_fields_and_reasons():
    evidence = _evidence(
        operator_approval=replace(
            _evidence().operator_approval,
            rejection_reasons=("stage5:manual_operator_note",),
        ),
        rejection_reasons=("stage5:bundle_note",),
    )
    payload = portfolio.stage5_runtime_evidence_bundle_to_dict(evidence)
    restored = portfolio.stage5_runtime_evidence_bundle_from_dict(payload)

    assert json.dumps(payload)
    assert restored == evidence
    assert restored.operator_approval.rejection_reasons == ("stage5:manual_operator_note",)
    assert restored.rejection_reasons == ("stage5:bundle_note",)


def test_no_evidence_path_remains_stage5_gate_missing():
    assert portfolio.stage5_live_readiness_blockers(None) == (portfolio.STAGE5_LIVE_READINESS_GATE_MISSING,)


def test_existing_ingestion_consumes_valid_evidence_gate_and_decision_pack_is_live_ready():
    orchestrator = _orchestrator()

    orchestrator.apply_stage5_live_readiness_gate_to_sleeve(_SLEEVE_ID, _build_gate(_evidence()))
    pack_payload = decision_pack_to_dict(orchestrator.decision_pack())

    assert pack_payload["stage5_live_ready"] is True
    assert pack_payload["stage5_live_ready_sleeve_ids"] == [_SLEEVE_ID]


def test_existing_ingestion_surfaces_failed_evidence_blockers_in_decision_pack():
    evidence = _evidence(
        operator_approval=replace(_evidence().operator_approval, approved=False),
    )
    orchestrator = _orchestrator()

    orchestrator.apply_stage5_live_readiness_gate_to_sleeve(_SLEEVE_ID, _build_gate(evidence))
    pack_payload = decision_pack_to_dict(orchestrator.decision_pack())

    assert pack_payload["stage5_live_ready"] is False
    assert pack_payload["stage5_live_readiness_blockers"] == ["stage5:operator_approval_missing"]


def test_combined_status_dict_remains_json_safe_after_evidence_gate_ingestion():
    orchestrator = _orchestrator()

    orchestrator.apply_stage5_live_readiness_gate_to_sleeve(_SLEEVE_ID, _build_gate(_evidence()))
    status = orchestrator.combined_status_dict()

    assert json.dumps(status)
    assert status["sleeve_portfolio"]["sleeves"][0]["promotion_candidate"]["stage5_live_ready"] is True


def test_no_live_execution_client_or_credential_code_path_is_introduced(monkeypatch):
    monkeypatch.setenv("CRYPTO_LIVE_API_KEY", "must-not-be-read")
    gate = _build_gate(
        _evidence(
            credential_attestation=replace(
                _evidence().credential_attestation,
                live_api_credentials_valid=False,
            )
        )
    )
    decision = ExecutionEngine(ExecutionConfig(mode=ExecutionMode.LIVE)).execute(_execution_request())

    assert gate.rejection_reasons == ("stage5:live_api_credentials_not_verified",)
    assert decision.allowed is False
    assert decision.rejection_reason == RejectionReason.LIVE_NOT_ENABLED


def test_repeated_same_runtime_evidence_output_is_deterministic():
    def payload() -> dict:
        gate = _build_gate(_evidence())
        return portfolio.stage5_live_readiness_gate_to_dict(gate)

    assert payload() == payload()
