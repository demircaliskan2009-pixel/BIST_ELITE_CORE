from __future__ import annotations

import json
from unittest.mock import MagicMock

from crypto_core.edge.models import EdgeFamily, EdgeSignal, SignalDirection
from crypto_core.execution.engine import ExecutionConfig, ExecutionEngine
from crypto_core.execution.models import ExecutionMode, ExecutionRequest, OrderIntent, RejectionReason
from crypto_core.guard.models import NoTradeDecision
from crypto_core.risk.models import RiskDecision, RiskEvaluation
from crypto_core.service.artifact_export import (
    EscalationStage,
    OperatorDecisionPack,
    decision_pack_to_dict,
    escalation_decision_to_dict,
)
from crypto_core.service.service_orchestrator import ServiceOrchestrator
from crypto_core.state.models import SystemState


def _pack(
    *,
    readiness_level: str = "tiny_cap_live",
    readiness_is_supportive: bool = True,
    promotion_verdict: str = "promote",
    warning_criteria: tuple[str, ...] = (),
    fail_criteria: tuple[str, ...] = (),
    insufficient_evidence: tuple[str, ...] = (),
    external_regime_quality: str = "supportive",
    external_regime_evidence_sufficient: bool = True,
    external_regime_concerns: tuple[str, ...] = (),
    stage5_live_ready: bool = False,
    stage5_live_readiness_blockers: tuple[str, ...] = ("stage5:stage4_comparison_missing",),
) -> OperatorDecisionPack:
    return OperatorDecisionPack(
        artifact_time_ns=1,
        review_id="review-20l",
        review_timestamp_ns=1,
        review_status="active",
        promotion_verdict=promotion_verdict,
        operator_disposition="promotable",
        decision_summary="phase20l decision pack",
        readiness_level=readiness_level,
        readiness_is_supportive=readiness_is_supportive,
        criteria_summary={"readiness": {"available": True}},
        pass_criteria=("promotion_review_supported",),
        warning_criteria=warning_criteria,
        fail_criteria=fail_criteria,
        insufficient_evidence=insufficient_evidence,
        stage5_live_ready=stage5_live_ready,
        stage5_live_ready_sleeve_ids=("sleeve-20l",) if stage5_live_ready else (),
        stage5_live_readiness_blockers=stage5_live_readiness_blockers,
        external_regime_quality=external_regime_quality,
        external_regime_evidence_available=True,
        external_regime_evidence_sufficient=external_regime_evidence_sufficient,
        external_regime_concerns=external_regime_concerns,
        reason_codes={"pass_count": 1, "warning_count": 0, "fail_count": 0, "insufficient_count": 0},
    )


def _decision(pack: OperatorDecisionPack):
    orchestrator = ServiceOrchestrator(service=MagicMock(), readiness_level="paper_live")
    return orchestrator._build_escalation_decision(pack)


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


def test_tiny_cap_live_review_eligible_requires_stage5_live_ready():
    pack = _pack(
        stage5_live_ready=False,
        stage5_live_readiness_blockers=("stage5:stage4_comparison_missing",),
    )

    decision = _decision(pack)

    assert decision.escalation_stage == EscalationStage.SHADOW_LIVE_REVIEW_ELIGIBLE
    assert decision.escalation_stage != EscalationStage.TINY_CAP_LIVE_REVIEW_ELIGIBLE
    assert decision_pack_to_dict(pack)["stage5_live_readiness_blockers"] == ["stage5:stage4_comparison_missing"]


def test_tiny_cap_live_review_eligible_allowed_when_stage5_ready_and_no_blockers():
    decision = _decision(
        _pack(
            stage5_live_ready=True,
            stage5_live_readiness_blockers=(),
        )
    )

    assert decision.escalation_stage == EscalationStage.TINY_CAP_LIVE_REVIEW_ELIGIBLE


def test_tiny_cap_live_review_eligible_blocked_when_ready_flag_true_but_blockers_exist():
    decision = _decision(
        _pack(
            stage5_live_ready=True,
            stage5_live_readiness_blockers=("stage5:operator_approval_missing",),
        )
    )

    assert decision.escalation_stage == EscalationStage.SHADOW_LIVE_REVIEW_ELIGIBLE
    assert decision.escalation_stage != EscalationStage.TINY_CAP_LIVE_REVIEW_ELIGIBLE


def test_tiny_cap_live_review_eligible_blocked_when_ready_false_even_without_blockers():
    decision = _decision(
        _pack(
            stage5_live_ready=False,
            stage5_live_readiness_blockers=(),
        )
    )

    assert decision.escalation_stage == EscalationStage.SHADOW_LIVE_REVIEW_ELIGIBLE
    assert decision.escalation_stage != EscalationStage.TINY_CAP_LIVE_REVIEW_ELIGIBLE


def test_shadow_live_or_lower_escalation_paths_unchanged_by_stage5_guard():
    decision = _decision(
        _pack(
            readiness_level="shadow_live",
            stage5_live_ready=False,
            stage5_live_readiness_blockers=("stage5:stage4_comparison_missing",),
        )
    )

    assert decision.escalation_stage == EscalationStage.SHADOW_LIVE_REVIEW_ELIGIBLE


def test_tiny_cap_live_downgrades_on_adverse_regime_even_when_stage5_ready():
    decision = _decision(
        _pack(
            external_regime_quality="cautionary",
            external_regime_evidence_sufficient=False,
            external_regime_concerns=("quality:cautionary",),
            stage5_live_ready=True,
            stage5_live_readiness_blockers=(),
        )
    )

    assert decision.escalation_stage == EscalationStage.SHADOW_LIVE_REVIEW_ELIGIBLE
    assert decision.escalation_stage != EscalationStage.TINY_CAP_LIVE_REVIEW_ELIGIBLE
    assert "external_regime:quality:cautionary" in decision.why_not_higher


def test_escalation_decision_json_safe_after_stage5_guard():
    decision = _decision(
        _pack(
            stage5_live_ready=False,
            stage5_live_readiness_blockers=("stage5:stage4_comparison_missing",),
        )
    )

    assert json.dumps(escalation_decision_to_dict(decision))


def test_phase20l_does_not_enable_live_execution():
    decision = ExecutionEngine(ExecutionConfig(mode=ExecutionMode.LIVE)).execute(_execution_request())

    assert decision.allowed is False
    assert decision.rejection_reason == RejectionReason.LIVE_NOT_ENABLED
