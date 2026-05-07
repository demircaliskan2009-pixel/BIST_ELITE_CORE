from __future__ import annotations

from dataclasses import replace

import pytest

import crypto_core.service.sleeve_portfolio as portfolio
import crypto_core.validation as validation
from crypto_core.edge.models import EdgeFamily, EdgeSignal, SignalDirection
from crypto_core.execution.engine import ExecutionConfig, ExecutionEngine
from crypto_core.execution.models import ExecutionMode, ExecutionRequest, OrderIntent, RejectionReason
from crypto_core.guard.models import NoTradeDecision
from crypto_core.risk.models import RiskDecision, RiskEvaluation
from crypto_core.state.models import SystemState

_DAY_NS = 86_400 * 1_000_000_000
_EDGE_ID = "edge-20n"
_OTHER_EDGE_ID = "edge-20n-other"
_SLEEVE_ID = "sleeve-20n"


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


def _baseline(*, edge_id: str = _EDGE_ID) -> validation.Stage4BacktestBaseline:
    return validation.Stage4BacktestBaseline(
        baseline_id="baseline-20n",
        edge_id=edge_id,
        as_of_ns=31 * _DAY_NS,
        backtest_sharpe=2.0,
        backtest_hit_rate=0.60,
        backtest_slippage_bps=4.0,
        backtest_fill_rate=0.98,
        source_window_ids=("wf-20n",),
    )


def _paper_summary(*, edge_id: str = _EDGE_ID, passed: bool = True) -> validation.Stage4PaperSummary:
    return validation.Stage4PaperSummary(
        paper_id="paper-20n-pass" if passed else "paper-20n-fail",
        edge_id=edge_id,
        started_at_ns=1,
        stopped_at_ns=31 * _DAY_NS + 1,
        paper_sharpe=1.2 if passed else 0.1,
        paper_hit_rate=0.58 if passed else 0.30,
        paper_slippage_bps=4.5 if passed else 20.0,
        paper_fill_rate=0.97 if passed else 0.50,
        paper_trade_count=42 if passed else 1,
    )


def _stage4_pass(*, edge_id: str = _EDGE_ID) -> validation.Stage4ComparisonResult:
    return validation.compare_stage4(_baseline(edge_id=edge_id), _paper_summary(edge_id=edge_id))


def _stage4_fail(*, edge_id: str = _EDGE_ID) -> validation.Stage4ComparisonResult:
    return validation.compare_stage4(
        _baseline(edge_id=edge_id),
        _paper_summary(edge_id=edge_id, passed=False),
    )


def _gate(**overrides: object) -> portfolio.Stage5LiveReadinessGate:
    values: dict[str, object] = {
        "edge_id": _EDGE_ID,
        "allocation_tier_pct": 10.0,
        "weeks_at_tier": 0,
        "as_of_ns": 100 * _DAY_NS,
        "stage4_passed": True,
        "operator_approval_recorded": True,
        "live_api_credentials_valid": True,
        "kill_switch_clear": True,
        "risk_governance_clear": True,
        "rejection_reasons": (),
    }
    values.update(overrides)
    return portfolio.build_stage5_live_readiness_gate(**values)  # type: ignore[arg-type]


def _sleeve(
    *,
    stage4_result: validation.Stage4ComparisonResult | None = "PASS_DEFAULT",  # type: ignore[assignment]
    stage5_gate: portfolio.Stage5LiveReadinessGate | None = None,
    edge_id: str = _EDGE_ID,
) -> portfolio.CryptoSleeveState:
    resolved_stage4 = _stage4_pass(edge_id=edge_id) if stage4_result == "PASS_DEFAULT" else stage4_result
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
            ("campaign-20n",),
        ),
        promotion_support=portfolio.SleevePromotionSupportResult(
            portfolio.SleevePromotionSupportStatus.SUPPORTIVE,
            True,
            portfolio.SleeveCampaignEvidenceStatus.CAMPAIGN_SUPPORTED,
            portfolio.SleeveQualificationStatus.PAPER_QUALIFIED,
            portfolio.SleeveRecommendationStatus.RECOMMENDED_ACTIVE,
        ),
        validation_pipeline_result=_pipeline_ready(),
        stage4_backtest_baseline=_baseline(edge_id=edge_id),
        stage4_comparison_result=resolved_stage4,
        stage5_entry_gate=stage5_gate,
    )


def _execution_request() -> ExecutionRequest:
    edge_signal = EdgeSignal(
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
            edge_signal=edge_signal,
            no_trade_decision=NoTradeDecision.allow(),
            evidence={},
            timestamp_ns=100,
        ),
        timestamp_ns=100,
    )


def test_deserialized_manual_gate_missing_stage4_is_normalized_fail_closed():
    payload = portfolio.crypto_sleeve_state_to_dict(
        _sleeve(
            stage4_result=None,
            stage5_gate=_gate(),
        )
    )

    restored = portfolio.crypto_sleeve_state_from_dict(payload)

    assert restored.stage5_entry_gate is not None
    assert restored.stage5_entry_gate.passed is False
    assert restored.stage5_entry_gate.stage4_passed is False
    assert "stage5:stage4_comparison_missing" in restored.stage5_entry_gate.rejection_reasons
    assert "stage5:stage4_not_passed" not in restored.stage5_entry_gate.rejection_reasons
    assert portfolio.stage5_live_ready(restored.stage5_entry_gate) is False


def test_deserialized_manual_gate_failed_stage4_is_normalized_fail_closed():
    payload = portfolio.crypto_sleeve_state_to_dict(
        _sleeve(
            stage4_result=_stage4_fail(),
            stage5_gate=_gate(),
        )
    )

    restored = portfolio.crypto_sleeve_state_from_dict(payload)

    assert restored.stage5_entry_gate is not None
    assert restored.stage5_entry_gate.passed is False
    assert restored.stage5_entry_gate.stage4_passed is False
    assert "stage5:stage4_not_passed" in restored.stage5_entry_gate.rejection_reasons
    assert "stage5:stage4_comparison_missing" not in restored.stage5_entry_gate.rejection_reasons
    assert portfolio.stage5_live_ready(restored.stage5_entry_gate) is False


def test_deserialized_manual_gate_passing_stage4_preserves_live_ready_metadata():
    payload = portfolio.crypto_sleeve_state_to_dict(_sleeve(stage5_gate=_gate()))

    restored = portfolio.crypto_sleeve_state_from_dict(payload)

    assert restored.stage5_entry_gate is not None
    assert portfolio.stage5_live_ready(restored.stage5_entry_gate) is True


def test_deserialized_manual_gate_edge_mismatch_fails_closed():
    payload = portfolio.crypto_sleeve_state_to_dict(
        _sleeve(
            stage4_result=_stage4_pass(edge_id=_EDGE_ID),
            stage5_gate=_gate(edge_id=_OTHER_EDGE_ID),
        )
    )

    with pytest.raises(portfolio.SleevePortfolioCorruptError, match="stage5 gate edge_id"):
        portfolio.crypto_sleeve_state_from_dict(payload)


def test_deserialized_manual_gate_normalization_is_deterministic():
    payload = portfolio.crypto_sleeve_state_to_dict(
        _sleeve(
            stage4_result=None,
            stage5_gate=_gate(rejection_reasons=("stage5:operator_approval_missing",)),
        )
    )

    first = portfolio.crypto_sleeve_state_from_dict(payload)
    second = portfolio.crypto_sleeve_state_from_dict(payload)

    assert portfolio.crypto_sleeve_state_to_dict(first) == portfolio.crypto_sleeve_state_to_dict(second)


def test_stage5_deserialization_patch_does_not_enable_live_execution():
    sleeve = portfolio.crypto_sleeve_state_from_dict(
        portfolio.crypto_sleeve_state_to_dict(_sleeve(stage5_gate=_gate()))
    )

    decision = ExecutionEngine(ExecutionConfig(mode=ExecutionMode.LIVE)).execute(_execution_request())

    assert portfolio.stage5_live_ready(sleeve.stage5_entry_gate) is True
    assert decision.rejection_reason == RejectionReason.LIVE_NOT_ENABLED
