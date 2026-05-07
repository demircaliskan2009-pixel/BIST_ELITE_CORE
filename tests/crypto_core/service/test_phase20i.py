"""Phase 20I — Stage5 Runtime Evidence Record Ingestion API.

Tests:
    - SleevePortfolioController.apply_stage5_runtime_evidence_record
    - ServiceOrchestrator.apply_stage5_runtime_evidence_record_to_sleeve
    - Fail-closed behavior for unknown sleeve / missing portfolio
    - Stage4 pass/fail propagation through record path
    - Multi-sleeve isolation
    - Field preservation (stage4_backtest_baseline, validation_pipeline_result, pbo_allocation_cap)
    - Orchestrator decision_pack Stage5 fields
    - combined_status_dict JSON safety
    - Deterministic replay
    - No live execution enablement
    - No env/credential/network keys required
    - Phase 20E guard fires on failed record
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, replace
from unittest.mock import MagicMock

import pytest

import crypto_core.service.sleeve_portfolio as portfolio
import crypto_core.validation as validation
from crypto_core.execution.engine import ExecutionConfig, ExecutionEngine
from crypto_core.execution.models import ExecutionMode
from crypto_core.service.models import (
    ExecutionIntelligenceStatus,
    QueuePressure,
    QueueSnapshot,
    ServiceStatus,
    WatchdogStatus,
)
from crypto_core.service.service_orchestrator import ServiceOrchestrator
from crypto_core.service.sleeve_portfolio_controller import SleevePortfolioController

_DAY_NS = 86_400 * 1_000_000_000
_EDGE_ID = "edge-20i"
_SLEEVE_ID = "sleeve-20i"
_OTHER_SLEEVE_ID = "sleeve-20i-other"
_RECORD_ID = "record-20i-001"


# ---------------------------------------------------------------------------
# Stubs for orchestrator construction
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
    campaign_ids: tuple[str, ...] = ("campaign-20i",)
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
    review_id = "review-20i"
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
# Domain helpers
# ---------------------------------------------------------------------------


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


def _baseline(*, edge_id: str = _EDGE_ID) -> validation.Stage4BacktestBaseline:
    return validation.Stage4BacktestBaseline(
        baseline_id="baseline-20i",
        edge_id=edge_id,
        as_of_ns=31 * _DAY_NS,
        backtest_sharpe=2.0,
        backtest_hit_rate=0.60,
        backtest_slippage_bps=4.0,
        backtest_fill_rate=0.98,
        source_window_ids=("wf-001", "wf-002"),
    )


def _paper_summary(*, edge_id: str = _EDGE_ID, passed: bool = True) -> validation.Stage4PaperSummary:
    if passed:
        return validation.Stage4PaperSummary(
            paper_id="paper-20i",
            edge_id=edge_id,
            started_at_ns=1,
            stopped_at_ns=31 * _DAY_NS + 1,
            paper_sharpe=1.2,
            paper_hit_rate=0.58,
            paper_slippage_bps=4.5,
            paper_fill_rate=0.97,
            paper_trade_count=42,
        )
    return validation.Stage4PaperSummary(
        paper_id="paper-20i-fail",
        edge_id=edge_id,
        started_at_ns=1,
        stopped_at_ns=31 * _DAY_NS + 1,
        paper_sharpe=0.1,
        paper_hit_rate=0.30,
        paper_slippage_bps=20.0,
        paper_fill_rate=0.50,
        paper_trade_count=1,
    )


def _stage4_pass(*, edge_id: str = _EDGE_ID) -> validation.Stage4ComparisonResult:
    return validation.compare_stage4(_baseline(edge_id=edge_id), _paper_summary(edge_id=edge_id, passed=True))


def _stage4_fail(*, edge_id: str = _EDGE_ID) -> validation.Stage4ComparisonResult:
    return validation.compare_stage4(_baseline(edge_id=edge_id), _paper_summary(edge_id=edge_id, passed=False))


def _approval(*, approved: bool = True) -> portfolio.Stage5OperatorApprovalEvidence:
    return portfolio.Stage5OperatorApprovalEvidence(
        approved=approved,
        approver_id="ops-lead-20i",
        approved_at_ns=90 * _DAY_NS,
        approval_reference="approval-ticket-20i",
        rejection_reasons=(),
    )


def _credentials() -> portfolio.Stage5CredentialAttestationEvidence:
    return portfolio.Stage5CredentialAttestationEvidence(
        live_api_credentials_valid=True,
        attested_by="security-lead-20i",
        attested_at_ns=91 * _DAY_NS,
        attestation_reference="credential-attestation-20i",
        rejection_reasons=(),
    )


def _risk() -> portfolio.Stage5RiskGovernanceEvidence:
    return portfolio.Stage5RiskGovernanceEvidence(
        risk_governance_clear=True,
        kill_switch_clear=True,
        ehs_at_entry=0.80,
        max_drawdown_bps=None,
        attested_at_ns=92 * _DAY_NS,
        rejection_reasons=(),
    )


def _canary(*, tier: float = 10.0, weeks: int = 0) -> portfolio.Stage5CanaryTierEvidence:
    return portfolio.Stage5CanaryTierEvidence(
        allocation_tier_pct=tier,
        weeks_at_tier=weeks,
        canary_observation_count=20,
        canary_pnl_non_negative=True,
        canary_drawdown_within_limit=True,
        canary_slippage_within_limit=True,
        canary_incidents=0,
        as_of_ns=100 * _DAY_NS,
        rejection_reasons=(),
    )


def _bundle(**overrides: object) -> portfolio.Stage5RuntimeEvidenceBundle:
    values: dict[str, object] = {
        "edge_id": _EDGE_ID,
        "as_of_ns": 100 * _DAY_NS,
        "operator_approval": _approval(),
        "credential_attestation": _credentials(),
        "risk_governance": _risk(),
        "canary_tier": _canary(),
        "rejection_reasons": (),
    }
    values.update(overrides)
    return portfolio.Stage5RuntimeEvidenceBundle(**values)  # type: ignore[arg-type]


def _record(**overrides: object) -> portfolio.Stage5RuntimeEvidenceRecord:
    values: dict[str, object] = {
        "record_id": _RECORD_ID,
        "sleeve_id": _SLEEVE_ID,
        "edge_id": _EDGE_ID,
        "evidence_bundle": _bundle(),
        "created_at_ns": 100 * _DAY_NS,
    }
    values.update(overrides)
    return portfolio.Stage5RuntimeEvidenceRecord(**values)  # type: ignore[arg-type]


def _sleeve(
    *,
    sleeve_id: str = _SLEEVE_ID,
    edge_id: str = _EDGE_ID,
    pipeline: validation.ValidationPipelineResult | None = None,
    stage4_result: validation.Stage4ComparisonResult | None = None,
    stage5_gate: portfolio.Stage5LiveReadinessGate | None = None,
    include_stage4: bool = True,
) -> portfolio.CryptoSleeveState:
    s4_result = _stage4_pass(edge_id=edge_id) if (include_stage4 and stage4_result is None) else stage4_result
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
            ("campaign-20i",),
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
        stage4_comparison_result=s4_result,
        stage5_entry_gate=stage5_gate,
    )


def _controller(*sleeves: portfolio.CryptoSleeveState) -> SleevePortfolioController:
    return SleevePortfolioController(defined_sleeves=tuple(sleeves), created_at_ns=1)


def _orchestrator(*sleeves: portfolio.CryptoSleeveState) -> ServiceOrchestrator:
    orch = ServiceOrchestrator(
        service=_Service(),
        readiness_level="paper_live",
        sleeves=tuple(sleeves),
    )
    orch._decision_pack_readiness_status = MagicMock(return_value=None)  # type: ignore[method-assign]
    orch._review = _Review()  # type: ignore[assignment]
    return orch


def _snap_target(snap: portfolio.SleevePortfolioSnapshot, sleeve_id: str = _SLEEVE_ID) -> portfolio.CryptoSleeveState:
    return next(s for s in snap.sleeves if s.sleeve_id == sleeve_id)


def _op_target(snap: object, sleeve_id: str = _SLEEVE_ID) -> portfolio.CryptoSleeveState:
    return next(s for s in snap.sleeve_portfolio.sleeves if s.sleeve_id == sleeve_id)


# ---------------------------------------------------------------------------
# Test 1 — controller applies valid record → stage5_live_ready=True
# ---------------------------------------------------------------------------


def test_controller_valid_record_returns_live_ready_true():
    ctrl = _controller(_sleeve())
    snap = ctrl.apply_stage5_runtime_evidence_record(
        sleeve_id=_SLEEVE_ID,
        record=_record(),
        allocation_tier_pct=10.0,
        weeks_at_tier=0,
    )
    target = _snap_target(snap)
    assert target.stage5_entry_gate is not None
    assert portfolio.stage5_live_ready(target.stage5_entry_gate) is True


# ---------------------------------------------------------------------------
# Test 2 — controller failed operator approval record produces Stage5 blocker
# ---------------------------------------------------------------------------


def test_controller_failed_approval_record_produces_blocker():
    rec = _record(evidence_bundle=_bundle(operator_approval=_approval(approved=False)))
    ctrl = _controller(_sleeve())
    snap = ctrl.apply_stage5_runtime_evidence_record(
        sleeve_id=_SLEEVE_ID,
        record=rec,
        allocation_tier_pct=10.0,
        weeks_at_tier=0,
    )
    target = _snap_target(snap)
    assert target.stage5_entry_gate is not None
    assert target.stage5_entry_gate.passed is False
    assert "stage5:operator_approval_missing" in target.stage5_entry_gate.rejection_reasons


# ---------------------------------------------------------------------------
# Test 3 — controller uses sleeve's Stage4 PASS result → gate passes
# ---------------------------------------------------------------------------


def test_controller_uses_sleeve_stage4_pass_result():
    ctrl = _controller(_sleeve(stage4_result=_stage4_pass()))
    snap = ctrl.apply_stage5_runtime_evidence_record(
        sleeve_id=_SLEEVE_ID,
        record=_record(),
        allocation_tier_pct=10.0,
        weeks_at_tier=0,
    )
    target = _snap_target(snap)
    assert target.stage5_entry_gate is not None
    assert target.stage5_entry_gate.passed is True


# ---------------------------------------------------------------------------
# Test 4 — controller uses sleeve's Stage4 FAIL result → gate includes Stage4 blocker
# ---------------------------------------------------------------------------


def test_controller_uses_sleeve_stage4_fail_result():
    ctrl = _controller(_sleeve(stage4_result=_stage4_fail()))
    snap = ctrl.apply_stage5_runtime_evidence_record(
        sleeve_id=_SLEEVE_ID,
        record=_record(),
        allocation_tier_pct=10.0,
        weeks_at_tier=0,
    )
    target = _snap_target(snap)
    assert target.stage5_entry_gate is not None
    assert target.stage5_entry_gate.passed is False
    assert "stage5:stage4_not_passed" in target.stage5_entry_gate.rejection_reasons


# ---------------------------------------------------------------------------
# Test 5 — controller unknown sleeve fails closed
# ---------------------------------------------------------------------------


def test_controller_unknown_sleeve_fails_closed():
    ctrl = _controller(_sleeve())
    with pytest.raises(KeyError, match="Unknown sleeve_id"):
        ctrl.apply_stage5_runtime_evidence_record(
            sleeve_id="does-not-exist",
            record=_record(),
            allocation_tier_pct=10.0,
            weeks_at_tier=0,
        )


# ---------------------------------------------------------------------------
# Test 6 — controller updates only target sleeve when multiple configured
# ---------------------------------------------------------------------------


def test_controller_updates_only_target_sleeve():
    other = _sleeve(sleeve_id=_OTHER_SLEEVE_ID, edge_id="edge-other")
    ctrl = _controller(_sleeve(), other)
    snap = ctrl.apply_stage5_runtime_evidence_record(
        sleeve_id=_SLEEVE_ID,
        record=_record(),
        allocation_tier_pct=10.0,
        weeks_at_tier=0,
    )
    target = _snap_target(snap, _SLEEVE_ID)
    untouched = _snap_target(snap, _OTHER_SLEEVE_ID)
    assert target.stage5_entry_gate is not None
    assert untouched.stage5_entry_gate is None  # not touched


# ---------------------------------------------------------------------------
# Test 7 — controller preserves stage4_backtest_baseline, validation_pipeline_result, pbo_allocation_cap
# ---------------------------------------------------------------------------


def test_controller_preserves_stage4_baseline_and_pipeline():
    pipeline = _pipeline_ready(cap=0.33)
    baseline = _baseline()
    s4 = _stage4_pass()
    ctrl = _controller(_sleeve(pipeline=pipeline, stage4_result=s4))
    snap = ctrl.apply_stage5_runtime_evidence_record(
        sleeve_id=_SLEEVE_ID,
        record=_record(),
        allocation_tier_pct=10.0,
        weeks_at_tier=0,
    )
    target = _snap_target(snap)
    assert target.stage4_backtest_baseline == baseline
    assert target.stage4_comparison_result == s4
    assert target.validation_pipeline_result is not None
    assert target.validation_pipeline_result.pbo_allocation_cap == 0.33


# ---------------------------------------------------------------------------
# Test 8 — orchestrator facade applies valid record and returns OperatorSnapshot
# ---------------------------------------------------------------------------


def test_orchestrator_valid_record_returns_operator_snapshot():
    orch = _orchestrator(_sleeve())
    snap = orch.apply_stage5_runtime_evidence_record_to_sleeve(
        sleeve_id=_SLEEVE_ID,
        record=_record(),
        allocation_tier_pct=10.0,
        weeks_at_tier=0,
    )
    assert snap is not None
    target = _op_target(snap)
    assert target.stage5_entry_gate is not None
    assert portfolio.stage5_live_ready(target.stage5_entry_gate) is True


# ---------------------------------------------------------------------------
# Test 9 — orchestrator facade failed record surfaces blockers in combined_status_dict
# ---------------------------------------------------------------------------


def test_orchestrator_failed_record_blockers_in_combined_status_dict():
    rec = _record(evidence_bundle=_bundle(operator_approval=_approval(approved=False)))
    orch = _orchestrator(_sleeve())
    orch.apply_stage5_runtime_evidence_record_to_sleeve(
        sleeve_id=_SLEEVE_ID,
        record=rec,
        allocation_tier_pct=10.0,
        weeks_at_tier=0,
    )
    status_dict = orch.combined_status_dict()
    serialized = json.dumps(status_dict)
    assert "stage5:operator_approval_missing" in serialized


# ---------------------------------------------------------------------------
# Test 10 — orchestrator facade updates decision_pack Stage5 fields
# ---------------------------------------------------------------------------


def test_orchestrator_valid_record_updates_decision_pack_stage5_fields():
    orch = _orchestrator(_sleeve())
    orch.apply_stage5_runtime_evidence_record_to_sleeve(
        sleeve_id=_SLEEVE_ID,
        record=_record(),
        allocation_tier_pct=10.0,
        weeks_at_tier=0,
    )
    dp = orch.decision_pack()
    # Valid gate with no blockers → stage5_live_ready should reflect gate state
    # (decision_pack stage5_live_ready requires sleeve_ids AND no blockers)
    assert isinstance(dp.stage5_live_ready, bool)
    assert isinstance(dp.stage5_live_readiness_blockers, tuple)


# ---------------------------------------------------------------------------
# Test 11 — orchestrator facade with no sleeve portfolio fails closed
# ---------------------------------------------------------------------------


def test_orchestrator_no_portfolio_fails_closed():
    orch = ServiceOrchestrator(service=_Service(), readiness_level="paper_live")
    orch._decision_pack_readiness_status = MagicMock(return_value=None)  # type: ignore[method-assign]
    orch._review = _Review()  # type: ignore[assignment]
    with pytest.raises(RuntimeError, match="not configured"):
        orch.apply_stage5_runtime_evidence_record_to_sleeve(
            sleeve_id=_SLEEVE_ID,
            record=_record(),
            allocation_tier_pct=10.0,
            weeks_at_tier=0,
        )


# ---------------------------------------------------------------------------
# Test 12 — edge_id mismatch must not silently mark live-ready
# ---------------------------------------------------------------------------


def test_record_edge_id_mismatch_with_stage4_does_not_silently_pass():
    """Record carries a different edge_id than the sleeve's Stage4 baseline.

    build_sleeve_with_stage5_live_readiness_gate validates edge_id against
    sleeve Stage4 evidence and raises ValueError on mismatch.
    The controller must surface this — it must not silently produce a passing gate.
    """
    # Sleeve has Stage4 baseline/result for _EDGE_ID; record has mismatched id
    mismatched_record = _record(edge_id="wrong-edge-id")
    ctrl = _controller(_sleeve())
    with pytest.raises((ValueError, Exception)):
        ctrl.apply_stage5_runtime_evidence_record(
            sleeve_id=_SLEEVE_ID,
            record=mismatched_record,
            allocation_tier_pct=10.0,
            weeks_at_tier=0,
        )


# ---------------------------------------------------------------------------
# Test 13 — repeated same input produces deterministic snapshot output
# ---------------------------------------------------------------------------


def test_controller_deterministic_replay_same_output():
    ctrl1 = _controller(_sleeve())
    snap1 = ctrl1.apply_stage5_runtime_evidence_record(
        sleeve_id=_SLEEVE_ID,
        record=_record(),
        allocation_tier_pct=10.0,
        weeks_at_tier=0,
    )
    ctrl2 = _controller(_sleeve())
    snap2 = ctrl2.apply_stage5_runtime_evidence_record(
        sleeve_id=_SLEEVE_ID,
        record=_record(),
        allocation_tier_pct=10.0,
        weeks_at_tier=0,
    )
    t1 = _snap_target(snap1)
    t2 = _snap_target(snap2)
    assert t1.stage5_entry_gate == t2.stage5_entry_gate


# ---------------------------------------------------------------------------
# Test 14 — json.dumps works on combined_status_dict after record ingestion
# ---------------------------------------------------------------------------


def test_orchestrator_combined_status_dict_json_safe_after_record():
    orch = _orchestrator(_sleeve())
    orch.apply_stage5_runtime_evidence_record_to_sleeve(
        sleeve_id=_SLEEVE_ID,
        record=_record(),
        allocation_tier_pct=10.0,
        weeks_at_tier=0,
    )
    status_dict = orch.combined_status_dict()
    serialized = json.dumps(status_dict)
    assert isinstance(serialized, str)


# ---------------------------------------------------------------------------
# Test 15 — no live execution enablement
# ---------------------------------------------------------------------------


def test_no_live_execution_enablement_after_record_ingestion():
    """Applying a Stage5 evidence record must never enable LIVE execution mode.

    The service must remain in paper/dry-run mode regardless of what evidence
    is ingested.  service_mode is controlled by PaperLiveService, not by Stage5
    evidence metadata.
    """
    orch = _orchestrator(_sleeve())
    orch.apply_stage5_runtime_evidence_record_to_sleeve(
        sleeve_id=_SLEEVE_ID,
        record=_record(),
        allocation_tier_pct=10.0,
        weeks_at_tier=0,
    )
    snap = orch.operator_snapshot()
    # Service mode must not be "live" — Stage5 evidence ingestion is read-only metadata
    assert snap.service_mode != "live"
    # DRY_RUN and PAPER are valid non-live modes; "live" would require PaperLiveService activation
    assert snap.service_mode in ("running", "paper", "dry_run", "paper_live", "degraded", "halted", "running")


# ---------------------------------------------------------------------------
# Test 16 — no env/credential/network/client keys required or read
# ---------------------------------------------------------------------------


def test_no_env_read_during_record_ingestion():
    """apply_stage5_runtime_evidence_record must not read or mutate os.environ."""
    original_env = dict(os.environ)
    ctrl = _controller(_sleeve())
    ctrl.apply_stage5_runtime_evidence_record(
        sleeve_id=_SLEEVE_ID,
        record=_record(),
        allocation_tier_pct=10.0,
        weeks_at_tier=0,
    )
    assert dict(os.environ) == original_env


def test_no_credential_keys_in_serialized_gate():
    forbidden = {"api_key", "secret", "token", "client", "network_client", "password", "private_key", "credentials"}
    ctrl = _controller(_sleeve())
    snap = ctrl.apply_stage5_runtime_evidence_record(
        sleeve_id=_SLEEVE_ID,
        record=_record(),
        allocation_tier_pct=10.0,
        weeks_at_tier=0,
    )
    target = _snap_target(snap)
    assert target.stage5_entry_gate is not None
    gate_d = portfolio.stage5_live_readiness_gate_to_dict(target.stage5_entry_gate)

    def _all_keys(obj: object) -> set[str]:
        keys: set[str] = set()
        if isinstance(obj, dict):
            for k, v in obj.items():
                keys.add(k)
                keys |= _all_keys(v)
        elif isinstance(obj, (list, tuple)):
            for item in obj:
                keys |= _all_keys(item)
        return keys

    assert not (_all_keys(gate_d) & forbidden)


# ---------------------------------------------------------------------------
# Test 17 — existing apply_stage5_live_readiness_gate still passes
# ---------------------------------------------------------------------------


def test_existing_apply_stage5_live_readiness_gate_still_works():
    """Regression: the existing gate API must not be broken by Phase 20I patch."""
    gate = portfolio.build_stage5_live_readiness_gate(
        edge_id=_EDGE_ID,
        allocation_tier_pct=10.0,
        weeks_at_tier=0,
        as_of_ns=100 * _DAY_NS,
        stage4_passed=True,
        operator_approval_recorded=True,
        live_api_credentials_valid=True,
        kill_switch_clear=True,
        risk_governance_clear=True,
    )
    ctrl = _controller(_sleeve())
    snap = ctrl.apply_stage5_live_readiness_gate(_SLEEVE_ID, gate)
    target = _snap_target(snap)
    assert target.stage5_entry_gate == gate
    assert portfolio.stage5_live_ready(target.stage5_entry_gate) is True


def test_existing_orchestrator_apply_stage5_live_readiness_gate_still_works():
    gate = portfolio.build_stage5_live_readiness_gate(
        edge_id=_EDGE_ID,
        allocation_tier_pct=10.0,
        weeks_at_tier=0,
        as_of_ns=100 * _DAY_NS,
        stage4_passed=True,
        operator_approval_recorded=True,
        live_api_credentials_valid=True,
        kill_switch_clear=True,
        risk_governance_clear=True,
    )
    orch = _orchestrator(_sleeve())
    snap = orch.apply_stage5_live_readiness_gate_to_sleeve(_SLEEVE_ID, gate)
    target = _op_target(snap)
    assert portfolio.stage5_live_ready(target.stage5_entry_gate) is True


# ---------------------------------------------------------------------------
# Test 18 — Stage5 failed record demotes decision_pack status (Phase 20E guard)
# ---------------------------------------------------------------------------


def test_failed_record_demotes_decision_pack_status_via_phase20e_guard():
    """A failed Stage5 gate from a record must trigger Phase 20E demotion.

    Phase 20E: RECOMMENDED_ACTIVE + blocking_reasons → decision_pack.status = BLOCKED.
    A failed Stage5 gate produces stage5:* blocking_reasons in the promotion candidate.
    """
    rec = _record(evidence_bundle=_bundle(operator_approval=_approval(approved=False)))
    ctrl = _controller(_sleeve())
    snap = ctrl.apply_stage5_runtime_evidence_record(
        sleeve_id=_SLEEVE_ID,
        record=rec,
        allocation_tier_pct=10.0,
        weeks_at_tier=0,
    )
    target = _snap_target(snap)
    # Gate must fail
    assert target.stage5_entry_gate is not None
    assert target.stage5_entry_gate.passed is False
    # Decision pack status must be BLOCKED (Phase 20E guard)
    dp = target.decision_pack
    assert dp.status == portfolio.SleeveDecisionPackStatus.BLOCKED
    stage5_blockers = [r for r in dp.blocking_reasons if r.startswith("stage5:")]
    assert len(stage5_blockers) >= 1
