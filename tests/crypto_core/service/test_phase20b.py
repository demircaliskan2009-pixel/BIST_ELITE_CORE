from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from unittest.mock import MagicMock

import pytest

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
from crypto_core.service.service_orchestrator import ServiceOrchestrator, operator_snapshot_to_dict
from crypto_core.service.sleeve_portfolio_controller import SleevePortfolioController
from crypto_core.state.models import SystemState

_DAY_NS = 86_400 * 1_000_000_000
_EDGE_ID = "edge-20b"
_SLEEVE_ID = "sleeve-stage5"
_OTHER_SLEEVE_ID = "sleeve-other"


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
    campaign_ids: tuple[str, ...] = ("campaign-20b",)
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
    review_id = "review-20b"
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


def _pipeline_ready(*, cap: float | None = 0.5) -> validation.ValidationPipelineResult:
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
        pbo_allocation_cap=cap,
        rejection_reasons=(),
        missing_stages=(),
    )


def _baseline(*, edge_id: str = _EDGE_ID, baseline_id: str = "baseline-20b") -> validation.Stage4BacktestBaseline:
    return validation.Stage4BacktestBaseline(
        baseline_id=baseline_id,
        edge_id=edge_id,
        as_of_ns=31 * _DAY_NS,
        backtest_sharpe=2.0,
        backtest_hit_rate=0.60,
        backtest_slippage_bps=4.0,
        backtest_fill_rate=0.98,
        source_window_ids=("wf-001", "wf-002"),
    )


def _paper_summary(*, edge_id: str = _EDGE_ID, paper_sharpe: float = 1.2) -> validation.Stage4PaperSummary:
    return validation.Stage4PaperSummary(
        paper_id="paper-20b",
        edge_id=edge_id,
        started_at_ns=1,
        stopped_at_ns=31 * _DAY_NS + 1,
        paper_sharpe=paper_sharpe,
        paper_hit_rate=0.58,
        paper_slippage_bps=4.5,
        paper_fill_rate=0.97,
        paper_trade_count=42,
    )


def _stage4_pass(*, edge_id: str = _EDGE_ID) -> validation.Stage4ComparisonResult:
    return validation.compare_stage4(_baseline(edge_id=edge_id), _paper_summary(edge_id=edge_id))


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


def _sleeve(
    *,
    sleeve_id: str = _SLEEVE_ID,
    edge_id: str = _EDGE_ID,
    pipeline: validation.ValidationPipelineResult | None = None,
    stage5_gate: portfolio.Stage5LiveReadinessGate | None = None,
) -> portfolio.CryptoSleeveState:
    return portfolio.CryptoSleeveState(
        sleeve_id=sleeve_id,
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
            ("campaign-20b",),
        ),
        promotion_support=portfolio.SleevePromotionSupportResult(
            portfolio.SleevePromotionSupportStatus.SUPPORTIVE,
            True,
            portfolio.SleeveCampaignEvidenceStatus.CAMPAIGN_SUPPORTED,
            portfolio.SleeveQualificationStatus.PAPER_QUALIFIED,
            portfolio.SleeveRecommendationStatus.RECOMMENDED_ACTIVE,
        ),
        validation_pipeline_result=_pipeline_ready() if pipeline is None else pipeline,
        stage4_backtest_baseline=_baseline(edge_id=edge_id),
        stage4_comparison_result=_stage4_pass(edge_id=edge_id),
        stage5_entry_gate=stage5_gate,
    )


def _controller(*sleeves: portfolio.CryptoSleeveState) -> SleevePortfolioController:
    return SleevePortfolioController(defined_sleeves=tuple(sleeves), created_at_ns=1)


def _orchestrator(*sleeves: portfolio.CryptoSleeveState) -> ServiceOrchestrator:
    orchestrator = ServiceOrchestrator(
        service=_Service(),
        readiness_level="paper_live",
        sleeves=tuple(sleeves),
    )
    orchestrator._decision_pack_readiness_status = MagicMock(return_value=None)  # type: ignore[method-assign]
    orchestrator._review = _Review()  # type: ignore[assignment]
    return orchestrator


def _target(snapshot: portfolio.SleevePortfolioSnapshot, sleeve_id: str = _SLEEVE_ID) -> portfolio.CryptoSleeveState:
    return next(sleeve for sleeve in snapshot.sleeves if sleeve.sleeve_id == sleeve_id)


def _operator_target(snapshot: object, sleeve_id: str = _SLEEVE_ID) -> portfolio.CryptoSleeveState:
    return next(sleeve for sleeve in snapshot.sleeve_portfolio.sleeves if sleeve.sleeve_id == sleeve_id)


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


def test_pure_helper_attaches_passing_stage5_gate_to_sleeve():
    gate = _stage5_gate()

    updated = portfolio.build_sleeve_with_stage5_live_readiness_gate(_sleeve(), gate)

    assert updated.stage5_entry_gate == gate
    assert portfolio.stage5_live_ready(updated.stage5_entry_gate) is True


def test_pure_helper_rejects_stage5_gate_with_mismatched_stage4_edge_id():
    with pytest.raises(ValueError, match="stage5 gate edge_id does not match sleeve Stage4 evidence"):
        portfolio.build_sleeve_with_stage5_live_readiness_gate(
            _sleeve(edge_id=_EDGE_ID),
            _stage5_gate(edge_id="edge-mismatch"),
        )


def test_pure_helper_clears_stage5_gate_when_given_none():
    sleeve = _sleeve(stage5_gate=_stage5_gate())

    updated = portfolio.build_sleeve_with_stage5_live_readiness_gate(sleeve, None)

    assert updated.stage5_entry_gate is None


def test_controller_applies_passing_stage5_gate_only_to_target_sleeve():
    controller = _controller(_sleeve(), _sleeve(sleeve_id=_OTHER_SLEEVE_ID, edge_id="edge-other"))
    gate = _stage5_gate()

    snapshot = controller.apply_stage5_live_readiness_gate(_SLEEVE_ID, gate)

    assert _target(snapshot).stage5_entry_gate == gate
    assert _target(snapshot, _OTHER_SLEEVE_ID).stage5_entry_gate is None


def test_controller_preserves_stage4_validation_and_pbo_metadata():
    pipeline = _pipeline_ready(cap=0.25)
    sleeve = _sleeve(pipeline=pipeline)
    controller = _controller(sleeve)

    snapshot = controller.apply_stage5_live_readiness_gate(_SLEEVE_ID, _stage5_gate())
    updated = _target(snapshot)

    assert updated.stage4_comparison_result == sleeve.stage4_comparison_result
    assert updated.stage4_backtest_baseline == sleeve.stage4_backtest_baseline
    assert updated.validation_pipeline_result == pipeline
    assert updated.promotion_candidate.pbo_allocation_cap == 0.25


def test_controller_unknown_sleeve_fails_closed():
    controller = _controller(_sleeve())

    with pytest.raises(KeyError, match="Unknown sleeve_id 'missing-sleeve'"):
        controller.apply_stage5_live_readiness_gate("missing-sleeve", _stage5_gate())


def test_orchestrator_facade_applies_stage5_gate_to_operator_and_decision_pack():
    orchestrator = _orchestrator(_sleeve())

    snapshot = orchestrator.apply_stage5_live_readiness_gate_to_sleeve(_SLEEVE_ID, _stage5_gate())
    status = orchestrator.combined_status_dict()
    pack_payload = decision_pack_to_dict(orchestrator.decision_pack())

    assert _operator_target(snapshot).promotion_candidate.stage5_live_ready is True
    assert status["sleeve_portfolio"]["sleeves"][0]["promotion_candidate"]["stage5_live_ready"] is True
    assert pack_payload["stage5_live_ready"] is True
    assert pack_payload["stage5_live_ready_sleeve_ids"] == [_SLEEVE_ID]


def test_orchestrator_facade_missing_controller_fails_closed():
    orchestrator = ServiceOrchestrator(service=_Service(), readiness_level="paper_live")

    with pytest.raises(RuntimeError, match="Sleeve portfolio controller is not configured for Stage5 live-readiness"):
        orchestrator.apply_stage5_live_readiness_gate_to_sleeve(_SLEEVE_ID, _stage5_gate())


def test_stage5_failed_gate_surfaces_blockers_in_decision_pack_after_facade():
    orchestrator = _orchestrator(_sleeve())

    orchestrator.apply_stage5_live_readiness_gate_to_sleeve(
        _SLEEVE_ID,
        _stage5_gate(operator_approval_recorded=False),
    )
    pack_payload = decision_pack_to_dict(orchestrator.decision_pack())

    assert pack_payload["stage5_live_ready"] is False
    assert pack_payload["stage5_live_readiness_blockers"] == ["stage5:operator_approval_missing"]


def test_stage5_gate_does_not_change_promotion_review_escalation_verdict():
    orchestrator = _orchestrator(_sleeve())
    before = orchestrator.decision_pack()

    orchestrator.apply_stage5_live_readiness_gate_to_sleeve(_SLEEVE_ID, _stage5_gate())
    after = orchestrator.decision_pack()

    assert (
        orchestrator._build_escalation_decision(before).escalation_stage
        == orchestrator._build_escalation_decision(after).escalation_stage
    )


def test_no_live_execution_client_or_credential_path_is_introduced(monkeypatch):
    monkeypatch.setenv("CRYPTO_LIVE_API_KEY", "must-not-be-read")
    orchestrator = _orchestrator(_sleeve())

    orchestrator.apply_stage5_live_readiness_gate_to_sleeve(
        _SLEEVE_ID,
        _stage5_gate(live_api_credentials_valid=False),
    )
    decision = ExecutionEngine(ExecutionConfig(mode=ExecutionMode.LIVE)).execute(_execution_request())

    assert decision.allowed is False
    assert decision.rejection_reason == RejectionReason.LIVE_NOT_ENABLED


def test_repeated_same_stage5_input_produces_deterministic_operator_snapshot_output():
    def payload() -> dict:
        orchestrator = _orchestrator(_sleeve())
        snapshot = orchestrator.apply_stage5_live_readiness_gate_to_sleeve(_SLEEVE_ID, _stage5_gate())
        return operator_snapshot_to_dict(snapshot)

    assert payload() == payload()


def test_combined_status_is_json_safe_after_stage5_gate_apply():
    orchestrator = _orchestrator(_sleeve())

    orchestrator.apply_stage5_live_readiness_gate_to_sleeve(_SLEEVE_ID, _stage5_gate())
    status = orchestrator.combined_status_dict()

    assert json.dumps(status)
    assert status["sleeve_portfolio"]["sleeves"][0]["stage5_entry_gate"]["passed"] is True
