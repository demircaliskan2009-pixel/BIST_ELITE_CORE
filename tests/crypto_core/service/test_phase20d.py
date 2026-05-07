from __future__ import annotations

from dataclasses import dataclass, field, replace
from unittest.mock import MagicMock

import crypto_core.service.sleeve_portfolio as portfolio
import crypto_core.validation as validation
from crypto_core.edge.models import EdgeFamily, EdgeSignal, SignalDirection
from crypto_core.execution.engine import ExecutionConfig, ExecutionEngine
from crypto_core.execution.models import ExecutionMode, ExecutionRequest, OrderIntent, RejectionReason
from crypto_core.guard.models import NoTradeDecision
from crypto_core.risk.models import RiskDecision, RiskEvaluation
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
_EDGE_ID = "edge-20d"
_SLEEVE_ID = "sleeve-20d"


# ---------------------------------------------------------------------------
# Service / Review stubs
# ---------------------------------------------------------------------------


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
    campaign_ids: tuple[str, ...] = ("campaign-20d",)
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
    review_id = "review-20d"
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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
        baseline_id="baseline-20d",
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
        paper_id="paper-20d",
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
    """Build a passing Stage5 gate via direct builder (not evidence bundle)."""
    values: dict[str, object] = {
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
            ("campaign-20d",),
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
        stage5_entry_gate=stage5_gate,
    )


def _orchestrator(sleeve: portfolio.CryptoSleeveState | None = None) -> ServiceOrchestrator:
    orchestrator = ServiceOrchestrator(
        service=_Service(),
        readiness_level="paper_live",
        sleeves=(_sleeve() if sleeve is None else sleeve,),
    )
    orchestrator._decision_pack_readiness_status = MagicMock(return_value=None)  # type: ignore[method-assign]
    orchestrator._review = _Review()  # type: ignore[assignment]
    return orchestrator


def _candidate(sleeve: portfolio.CryptoSleeveState) -> portfolio.SleevePromotionCandidateResult:
    return portfolio._build_sleeve_promotion_candidate_result(sleeve)  # type: ignore[attr-defined]


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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_missing_stage5_gate_does_not_block_paper_candidate():
    # stage5_entry_gate=None must not add any stage5:* to blocking_reasons
    sleeve = _sleeve(stage5_gate=None)

    candidate = _candidate(sleeve)

    assert not any(r.startswith("stage5:") for r in candidate.blocking_reasons)


def test_failed_stage5_gate_adds_blocking_reason():
    # Failed operator approval → stage5:operator_approval_missing in blocking_reasons
    gate = _stage5_gate(operator_approval_recorded=False)
    sleeve = _sleeve(stage5_gate=gate)

    candidate = _candidate(sleeve)

    assert gate.passed is False
    assert "stage5:operator_approval_missing" in candidate.blocking_reasons


def test_failed_stage5_gate_preserves_stage5_metadata_field():
    # stage5_live_readiness_blockers field must still carry the detailed reasons
    gate = _stage5_gate(kill_switch_clear=False)
    sleeve = _sleeve(stage5_gate=gate)

    candidate = _candidate(sleeve)

    assert "stage5:kill_switch_not_clear" in candidate.stage5_live_readiness_blockers
    assert "stage5:kill_switch_not_clear" in candidate.blocking_reasons


def test_passing_stage5_gate_does_not_add_blocking_reason():
    # Passing gate → no stage5 blocker in blocking_reasons
    gate = _stage5_gate()
    sleeve = _sleeve(stage5_gate=gate)

    candidate = _candidate(sleeve)

    assert gate.passed is True
    assert candidate.stage5_live_ready is True
    assert not any(r.startswith("stage5:") for r in candidate.blocking_reasons)


def test_stage5_blocking_reasons_are_deduped_and_ordered():
    # Two failed conditions → two unique reasons in stable order, no duplicates
    gate = _stage5_gate(operator_approval_recorded=False, kill_switch_clear=False)
    sleeve = _sleeve(stage5_gate=gate)

    candidate = _candidate(sleeve)

    stage5_reasons = [r for r in candidate.blocking_reasons if r.startswith("stage5:")]
    assert "stage5:operator_approval_missing" in stage5_reasons
    assert "stage5:kill_switch_not_clear" in stage5_reasons
    # No duplicates
    assert len(stage5_reasons) == len(set(stage5_reasons))


def test_stage5_failed_gate_reaches_decision_pack_blocking_reasons():
    # Failed Stage5 gate must propagate through decision pack blocking_reasons
    gate = _stage5_gate(operator_approval_recorded=False)
    orchestrator = _orchestrator(_sleeve(stage5_gate=gate))

    status = orchestrator.combined_status_dict()
    sleeve_status = status["sleeve_portfolio"]["sleeves"][0]

    assert "stage5:operator_approval_missing" in sleeve_status["promotion_candidate"]["blocking_reasons"]
    assert "stage5:operator_approval_missing" in sleeve_status["decision_pack"]["blocking_reasons"]


def test_stage4_pass_alone_still_not_live_ready():
    # Stage4 PASS present, no Stage5 gate → stage5_live_ready=False, no stage5 blocker
    sleeve = _sleeve(stage5_gate=None)

    assert sleeve.stage4_comparison_result is not None
    assert sleeve.stage4_comparison_result.passed is True

    candidate = _candidate(sleeve)

    assert candidate.stage5_live_ready is False
    assert not any(r.startswith("stage5:") for r in candidate.blocking_reasons)


def test_admitted_active_alone_still_not_live_ready():
    # Full paper-eligible sleeve (RECOMMENDED_ACTIVE) without Stage5 gate
    # must not be live-ready and must not carry any stage5 blocking reason
    sleeve = _sleeve(stage5_gate=None)

    assert sleeve.recommendation.status == portfolio.SleeveRecommendationStatus.RECOMMENDED_ACTIVE

    candidate = _candidate(sleeve)

    assert candidate.stage5_live_ready is False
    assert not any(r.startswith("stage5:") for r in candidate.blocking_reasons)


def test_no_live_execution_enablement():
    # Stage5 Phase 20D introduces no ExecutionMode.LIVE path
    gate = _stage5_gate()  # fully passing gate
    sleeve = _sleeve(stage5_gate=gate)

    assert portfolio.stage5_live_ready(sleeve.stage5_entry_gate) is True

    # Despite passing Stage5 gate, live execution is still LIVE_NOT_ENABLED
    decision = ExecutionEngine(ExecutionConfig(mode=ExecutionMode.LIVE)).execute(_execution_request())

    assert decision.allowed is False
    assert decision.rejection_reason == RejectionReason.LIVE_NOT_ENABLED


def test_repeated_same_input_is_deterministic():
    # Same sleeve input must produce identical promotion candidate output
    gate = _stage5_gate(operator_approval_recorded=False)
    sleeve = _sleeve(stage5_gate=gate)

    first = _candidate(sleeve)
    second = _candidate(sleeve)

    assert first == second
    assert first.blocking_reasons == second.blocking_reasons
    assert first.stage5_live_readiness_blockers == second.stage5_live_readiness_blockers
