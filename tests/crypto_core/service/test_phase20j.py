"""Phase 20J — Stage5 Runtime Evidence Requires Matching Passed Stage4.

Invariant (Phase 20J):
    Stage5 runtime evidence cannot produce a passing / live-ready gate unless a
    matching Stage4ComparisonResult exists and has passed.

Tests:
    1. build_stage5_gate_from_runtime_evidence_record: stage4=None → fail + "stage5:stage4_comparison_missing"
    2. Controller: sleeve with no Stage4 → attached gate not live-ready + decision_pack not live-ready
    3. Orchestrator: sleeve with no Stage4 → combined_status_dict JSON contains missing-stage4 blocker
    4. Stage4 PASS + valid record → still passes (regression)
    5. Stage4 FAIL + valid record → still includes "stage5:stage4_not_passed" (regression)
    6. Stage4 edge_id mismatch → raises ValueError with message containing "edge_id"
    7. No live execution enablement after record ingestion on Stage4-missing sleeve
    8. Deterministic replay: same record + same Stage4-missing sleeve → same gate / same blockers
"""

from __future__ import annotations

import json
import os
from dataclasses import replace
from unittest.mock import MagicMock

import pytest

import crypto_core.service.sleeve_portfolio as portfolio
import crypto_core.validation as validation
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
_EDGE_ID = "edge-20j"
_SLEEVE_ID = "sleeve-20j"
_OTHER_EDGE_ID = "edge-20j-wrong"
_RECORD_ID = "record-20j-001"


# ---------------------------------------------------------------------------
# Orchestrator stub
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


class _ReviewSnapshot:
    updated_at_ns = 303
    provisional_verdict = "promote"
    provisional_summary = "ok"
    insufficient_evidence: tuple[str, ...] = ()
    is_ready_to_finalize = True
    campaign_ids: tuple[str, ...] = ("campaign-20j",)
    campaign_count = 1
    ext_regime_quality = "supportive"
    ext_regime_governance: dict = {}
    verdict_distribution: dict = {}
    execution_sufficiency: dict = {}
    symbol_breadth: dict = {}


class _ReviewStatus:
    value = "active"


class _Review:
    campaign_count = 1
    final_report = None
    is_finalized = False
    review_id = "review-20j"
    status = _ReviewStatus()

    def current_snapshot(self) -> _ReviewSnapshot:
        return _ReviewSnapshot()

    def get_promotion_reason_summary(self) -> dict:
        return {
            "pass_reasons": ("ok",),
            "warning_reasons": (),
            "fail_reasons": (),
            "insufficient_reasons": (),
            "pass_count": 1,
            "warning_count": 0,
            "fail_count": 0,
            "insufficient_count": 0,
        }

    def get_missing_evidence(self) -> dict:
        return {"insufficient_criteria": [], "warning_criteria": [], "fail_criteria": [], "message": "ok"}


# ---------------------------------------------------------------------------
# Domain helpers
# ---------------------------------------------------------------------------


def _pipeline_ready(*, cap: float | None = 0.5) -> validation.ValidationPipelineResult:
    stage = validation.ValidationPipelineStageStatus(
        stage="stage", ran=True, passed=True, skipped=False, rejection_reasons=()
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
        baseline_id="baseline-20j",
        edge_id=edge_id,
        as_of_ns=31 * _DAY_NS,
        backtest_sharpe=2.0,
        backtest_hit_rate=0.60,
        backtest_slippage_bps=4.0,
        backtest_fill_rate=0.98,
        source_window_ids=("wf-001",),
    )


def _paper_summary(*, edge_id: str = _EDGE_ID, passed: bool = True) -> validation.Stage4PaperSummary:
    if passed:
        return validation.Stage4PaperSummary(
            paper_id="paper-20j",
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
        paper_id="paper-20j-fail",
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
        approver_id="ops-lead-20j",
        approved_at_ns=90 * _DAY_NS,
        approval_reference="approval-ticket-20j",
        rejection_reasons=(),
    )


def _credentials() -> portfolio.Stage5CredentialAttestationEvidence:
    return portfolio.Stage5CredentialAttestationEvidence(
        live_api_credentials_valid=True,
        attested_by="security-lead-20j",
        attested_at_ns=91 * _DAY_NS,
        attestation_reference="credential-attestation-20j",
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


def _bundle(*, edge_id: str = _EDGE_ID, **overrides: object) -> portfolio.Stage5RuntimeEvidenceBundle:
    values: dict[str, object] = {
        "edge_id": edge_id,
        "as_of_ns": 100 * _DAY_NS,
        "operator_approval": _approval(),
        "credential_attestation": _credentials(),
        "risk_governance": _risk(),
        "canary_tier": _canary(),
        "rejection_reasons": (),
    }
    values.update(overrides)
    return portfolio.Stage5RuntimeEvidenceBundle(**values)  # type: ignore[arg-type]


def _record(*, edge_id: str = _EDGE_ID, **overrides: object) -> portfolio.Stage5RuntimeEvidenceRecord:
    values: dict[str, object] = {
        "record_id": _RECORD_ID,
        "sleeve_id": _SLEEVE_ID,
        "edge_id": edge_id,
        "evidence_bundle": _bundle(edge_id=edge_id),
        "created_at_ns": 100 * _DAY_NS,
    }
    values.update(overrides)
    return portfolio.Stage5RuntimeEvidenceRecord(**values)  # type: ignore[arg-type]


def _sleeve(
    *,
    sleeve_id: str = _SLEEVE_ID,
    edge_id: str = _EDGE_ID,
    stage4_result: validation.Stage4ComparisonResult | None = "PASS_DEFAULT",  # type: ignore[assignment]
    include_baseline: bool = True,
) -> portfolio.CryptoSleeveState:
    """Build a sleeve state.

    stage4_result defaults to a passing Stage4 result when sentinel "PASS_DEFAULT" is used.
    Pass None explicitly to build a sleeve with no Stage4 comparison.
    """
    if stage4_result == "PASS_DEFAULT":  # sentinel
        resolved = _stage4_pass(edge_id=edge_id)
    else:
        resolved = stage4_result  # may be None or a real result
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
            ("campaign-20j",),
        ),
        promotion_support=portfolio.SleevePromotionSupportResult(
            portfolio.SleevePromotionSupportStatus.SUPPORTIVE,
            True,
            portfolio.SleeveCampaignEvidenceStatus.CAMPAIGN_SUPPORTED,
            portfolio.SleeveQualificationStatus.PAPER_QUALIFIED,
            portfolio.SleeveRecommendationStatus.RECOMMENDED_ACTIVE,
        ),
        validation_pipeline_result=_pipeline_ready(),
        stage4_backtest_baseline=_baseline(edge_id=edge_id) if include_baseline else None,
        stage4_comparison_result=resolved,
        stage5_entry_gate=None,
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
# Test 1 — build_stage5_gate_from_runtime_evidence_record: stage4=None → fail
# ---------------------------------------------------------------------------


def test_build_gate_stage4_none_returns_failing_gate():
    """stage4_comparison_result=None must produce a failing gate with stable missing-stage4 code."""
    rec = _record()
    gate = portfolio.build_stage5_gate_from_runtime_evidence_record(
        rec,
        allocation_tier_pct=10.0,
        weeks_at_tier=0,
        stage4_comparison_result=None,
    )
    assert gate.passed is False
    assert gate.stage4_passed is False
    assert "stage5:stage4_comparison_missing" in gate.rejection_reasons


def test_build_gate_stage4_none_blocker_code_is_stable():
    """Deterministic: same input always produces identical rejection reason code."""
    rec = _record()
    gate1 = portfolio.build_stage5_gate_from_runtime_evidence_record(
        rec, allocation_tier_pct=10.0, weeks_at_tier=0, stage4_comparison_result=None
    )
    gate2 = portfolio.build_stage5_gate_from_runtime_evidence_record(
        rec, allocation_tier_pct=10.0, weeks_at_tier=0, stage4_comparison_result=None
    )
    assert gate1.rejection_reasons == gate2.rejection_reasons
    assert "stage5:stage4_comparison_missing" in gate1.rejection_reasons


def test_build_gate_stage4_none_other_evidence_blockers_preserved():
    """Missing Stage4 + failed approval → both blockers present; neither is swallowed."""
    rec = _record(evidence_bundle=_bundle(operator_approval=_approval(approved=False)))
    gate = portfolio.build_stage5_gate_from_runtime_evidence_record(
        rec,
        allocation_tier_pct=10.0,
        weeks_at_tier=0,
        stage4_comparison_result=None,
    )
    assert gate.passed is False
    assert "stage5:stage4_comparison_missing" in gate.rejection_reasons
    assert "stage5:operator_approval_missing" in gate.rejection_reasons


# ---------------------------------------------------------------------------
# Test 2 — controller: sleeve with no Stage4 → gate not live-ready
# ---------------------------------------------------------------------------


def test_controller_sleeve_missing_stage4_gate_not_live_ready():
    """Sleeve with stage4_comparison_result=None must produce a non-live-ready gate."""
    ctrl = _controller(_sleeve(stage4_result=None, include_baseline=False))
    snap = ctrl.apply_stage5_runtime_evidence_record(
        sleeve_id=_SLEEVE_ID,
        record=_record(),
        allocation_tier_pct=10.0,
        weeks_at_tier=0,
    )
    target = _snap_target(snap)
    assert target.stage5_entry_gate is not None
    assert target.stage5_entry_gate.passed is False
    assert portfolio.stage5_live_ready(target.stage5_entry_gate) is False
    assert "stage5:stage4_comparison_missing" in target.stage5_entry_gate.rejection_reasons


def test_controller_sleeve_missing_stage4_decision_pack_not_live_ready():
    """decision_pack must not be live-ready when Stage4 is missing."""
    ctrl = _controller(_sleeve(stage4_result=None, include_baseline=False))
    snap = ctrl.apply_stage5_runtime_evidence_record(
        sleeve_id=_SLEEVE_ID,
        record=_record(),
        allocation_tier_pct=10.0,
        weeks_at_tier=0,
    )
    target = _snap_target(snap)
    dp = target.decision_pack
    assert dp.status == portfolio.SleeveDecisionPackStatus.BLOCKED
    stage5_blockers = [r for r in dp.blocking_reasons if r.startswith("stage5:")]
    assert len(stage5_blockers) >= 1


# ---------------------------------------------------------------------------
# Test 3 — orchestrator: sleeve missing Stage4 → combined_status_dict JSON contains blocker
# ---------------------------------------------------------------------------


def test_orchestrator_missing_stage4_blockers_in_combined_status_dict():
    """combined_status_dict JSON must contain 'stage5:stage4_comparison_missing' blocker."""
    orch = _orchestrator(_sleeve(stage4_result=None, include_baseline=False))
    orch.apply_stage5_runtime_evidence_record_to_sleeve(
        sleeve_id=_SLEEVE_ID,
        record=_record(),
        allocation_tier_pct=10.0,
        weeks_at_tier=0,
    )
    status_dict = orch.combined_status_dict()
    serialized = json.dumps(status_dict)
    assert "stage5:stage4_comparison_missing" in serialized


def test_orchestrator_missing_stage4_json_safe():
    """combined_status_dict must remain JSON-serializable when Stage4 is missing."""
    orch = _orchestrator(_sleeve(stage4_result=None, include_baseline=False))
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
# Test 4 — Stage4 PASS + valid record → still passes (regression)
# ---------------------------------------------------------------------------


def test_stage4_pass_valid_record_gate_passes():
    """Passing Stage4 + all valid runtime evidence must still produce a passing gate."""
    rec = _record()
    gate = portfolio.build_stage5_gate_from_runtime_evidence_record(
        rec,
        allocation_tier_pct=10.0,
        weeks_at_tier=0,
        stage4_comparison_result=_stage4_pass(),
    )
    assert gate.passed is True
    assert gate.stage4_passed is True
    assert "stage5:stage4_comparison_missing" not in gate.rejection_reasons
    assert "stage5:stage4_not_passed" not in gate.rejection_reasons


def test_controller_stage4_pass_valid_record_live_ready():
    """Controller with passing Stage4 sleeve + valid record → live-ready gate."""
    ctrl = _controller(_sleeve())  # default fixture has passing Stage4
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
# Test 5 — Stage4 FAIL + valid record → still includes "stage5:stage4_not_passed" (regression)
# ---------------------------------------------------------------------------


def test_stage4_fail_valid_record_gate_fails_with_not_passed():
    """Failing Stage4 + valid runtime evidence must still include 'stage5:stage4_not_passed'."""
    rec = _record()
    gate = portfolio.build_stage5_gate_from_runtime_evidence_record(
        rec,
        allocation_tier_pct=10.0,
        weeks_at_tier=0,
        stage4_comparison_result=_stage4_fail(),
    )
    assert gate.passed is False
    assert gate.stage4_passed is False
    assert "stage5:stage4_not_passed" in gate.rejection_reasons
    # Must NOT add the "missing" code — that is distinct from "failed"
    assert "stage5:stage4_comparison_missing" not in gate.rejection_reasons


def test_controller_stage4_fail_sleeve_gate_fails_with_not_passed():
    """Controller with failing Stage4 sleeve must produce gate with 'stage5:stage4_not_passed'."""
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
# Test 6 — Stage4 edge_id mismatch → raises ValueError with message containing "edge_id"
# ---------------------------------------------------------------------------


def test_controller_edge_id_mismatch_raises_value_error():
    """Record.edge_id ≠ sleeve Stage4 baseline edge_id must raise ValueError (edge_id mismatch)."""
    mismatched_record = _record(edge_id=_OTHER_EDGE_ID)
    ctrl = _controller(_sleeve())  # sleeve has Stage4 baseline for _EDGE_ID
    with pytest.raises(ValueError, match="edge_id"):
        ctrl.apply_stage5_runtime_evidence_record(
            sleeve_id=_SLEEVE_ID,
            record=mismatched_record,
            allocation_tier_pct=10.0,
            weeks_at_tier=0,
        )


def test_build_gate_edge_id_mismatch_does_not_silently_produce_passing_gate():
    """Direct call: record.edge_id mismatch with Stage4 must not silently pass.

    build_stage5_gate_from_runtime_evidence_record produces the gate; the edge_id
    validation fires in build_sleeve_with_stage5_live_readiness_gate.  The entire
    controller path must not attach the gate when edge_ids diverge.
    """
    mismatched_record = _record(edge_id=_OTHER_EDGE_ID)
    # The gate itself carries the mismatched edge_id — it will be caught at attachment
    gate = portfolio.build_stage5_gate_from_runtime_evidence_record(
        mismatched_record,
        allocation_tier_pct=10.0,
        weeks_at_tier=0,
        stage4_comparison_result=_stage4_pass(),
    )
    # Gate's edge_id reflects the record's (mismatched) edge_id
    assert gate.edge_id == _OTHER_EDGE_ID
    # Attaching to a sleeve with different Stage4 edge_id must raise
    sleeve = _sleeve()  # Stage4 baseline edge_id = _EDGE_ID
    with pytest.raises(ValueError, match="edge_id"):
        portfolio.build_sleeve_with_stage5_live_readiness_gate(sleeve, gate)


# ---------------------------------------------------------------------------
# Test 7 — No live execution enablement after record ingestion on missing-Stage4 sleeve
# ---------------------------------------------------------------------------


def test_no_live_execution_enablement_missing_stage4():
    """service_mode must never be 'live' after applying record to a Stage4-missing sleeve."""
    orch = _orchestrator(_sleeve(stage4_result=None, include_baseline=False))
    orch.apply_stage5_runtime_evidence_record_to_sleeve(
        sleeve_id=_SLEEVE_ID,
        record=_record(),
        allocation_tier_pct=10.0,
        weeks_at_tier=0,
    )
    snap = orch.operator_snapshot()
    assert snap.service_mode != "live"


def test_no_env_read_missing_stage4():
    """apply_stage5_runtime_evidence_record must not read or mutate os.environ."""
    original_env = dict(os.environ)
    ctrl = _controller(_sleeve(stage4_result=None, include_baseline=False))
    ctrl.apply_stage5_runtime_evidence_record(
        sleeve_id=_SLEEVE_ID,
        record=_record(),
        allocation_tier_pct=10.0,
        weeks_at_tier=0,
    )
    assert dict(os.environ) == original_env


# ---------------------------------------------------------------------------
# Test 8 — Deterministic replay: same input → same gate
# ---------------------------------------------------------------------------


def test_deterministic_replay_missing_stage4():
    """Same record + same Stage4-missing sleeve → identical gate (both failing with same reasons)."""
    ctrl1 = _controller(_sleeve(stage4_result=None, include_baseline=False))
    snap1 = ctrl1.apply_stage5_runtime_evidence_record(
        sleeve_id=_SLEEVE_ID,
        record=_record(),
        allocation_tier_pct=10.0,
        weeks_at_tier=0,
    )
    ctrl2 = _controller(_sleeve(stage4_result=None, include_baseline=False))
    snap2 = ctrl2.apply_stage5_runtime_evidence_record(
        sleeve_id=_SLEEVE_ID,
        record=_record(),
        allocation_tier_pct=10.0,
        weeks_at_tier=0,
    )
    t1 = _snap_target(snap1)
    t2 = _snap_target(snap2)
    assert t1.stage5_entry_gate == t2.stage5_entry_gate


def test_deterministic_replay_passing_stage4():
    """Same record + passing Stage4 sleeve → identical passing gate on both runs."""
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
    assert t1.stage5_entry_gate is not None
    assert t1.stage5_entry_gate.passed is True


# ---------------------------------------------------------------------------
# Boundary: "missing" and "not_passed" codes are distinct and never confused
# ---------------------------------------------------------------------------


def test_stage4_missing_code_is_distinct_from_not_passed_code():
    """'stage5:stage4_comparison_missing' ≠ 'stage5:stage4_not_passed' — codes are never confused."""
    rec = _record()

    gate_missing = portfolio.build_stage5_gate_from_runtime_evidence_record(
        rec, allocation_tier_pct=10.0, weeks_at_tier=0, stage4_comparison_result=None
    )
    gate_failed = portfolio.build_stage5_gate_from_runtime_evidence_record(
        rec, allocation_tier_pct=10.0, weeks_at_tier=0, stage4_comparison_result=_stage4_fail()
    )

    assert "stage5:stage4_comparison_missing" in gate_missing.rejection_reasons
    assert "stage5:stage4_not_passed" not in gate_missing.rejection_reasons

    assert "stage5:stage4_not_passed" in gate_failed.rejection_reasons
    assert "stage5:stage4_comparison_missing" not in gate_failed.rejection_reasons


# ---------------------------------------------------------------------------
# Phase 20K — stage5_live_readiness_blockers blocker-function signal tests
# ---------------------------------------------------------------------------


def test_stage4_missing_blockers_do_not_emit_stage4_not_passed():
    """stage5_live_readiness_blockers must only emit 'stage4_comparison_missing', never 'stage4_not_passed', when Stage4 was never recorded."""
    rec = _record()
    gate = portfolio.build_stage5_gate_from_runtime_evidence_record(
        rec,
        allocation_tier_pct=10.0,
        weeks_at_tier=0,
        stage4_comparison_result=None,
    )
    blockers = portfolio.stage5_live_readiness_blockers(gate)
    assert "stage5:stage4_comparison_missing" in blockers
    assert "stage5:stage4_not_passed" not in blockers


def test_stage4_failed_blockers_emit_not_passed_not_missing():
    """stage5_live_readiness_blockers must only emit 'stage4_not_passed', never 'stage4_comparison_missing', when Stage4 comparison failed."""
    rec = _record()
    gate = portfolio.build_stage5_gate_from_runtime_evidence_record(
        rec,
        allocation_tier_pct=10.0,
        weeks_at_tier=0,
        stage4_comparison_result=_stage4_fail(),
    )
    blockers = portfolio.stage5_live_readiness_blockers(gate)
    assert "stage5:stage4_not_passed" in blockers
    assert "stage5:stage4_comparison_missing" not in blockers


def test_no_stage4_sleeve_wrong_edge_id_gate_attached_but_blocked():
    """A sleeve with no Stage4 baseline/comparison accepts a mismatched edge_id gate (reference_edge_ids=()).

    The gate must still be failed and not live-ready due to Stage4 missing evidence.
    This documents the intended behavior: edge_id enforcement is inactive when no Stage4
    reference exists, but Stage4 missing always blocks live-readiness independently.
    """
    # Build a gate for a different edge_id from what the sleeve uses
    wrong_record = _record(edge_id=_OTHER_EDGE_ID)
    gate = portfolio.build_stage5_gate_from_runtime_evidence_record(
        wrong_record,
        allocation_tier_pct=10.0,
        weeks_at_tier=0,
        stage4_comparison_result=None,  # Stage4 missing → gate.passed=False
    )
    # Sleeve has no Stage4 baseline or comparison — reference_edge_ids=() so no ValueError
    sleeve = _sleeve(stage4_result=None, include_baseline=False)
    attached_sleeve = portfolio.build_sleeve_with_stage5_live_readiness_gate(sleeve, gate)
    assert attached_sleeve.stage5_entry_gate is not None
    assert attached_sleeve.stage5_entry_gate.passed is False
    assert portfolio.stage5_live_ready(attached_sleeve.stage5_entry_gate) is False
    blockers = portfolio.stage5_live_readiness_blockers(attached_sleeve.stage5_entry_gate)
    assert "stage5:stage4_comparison_missing" in blockers
    assert "stage5:stage4_not_passed" not in blockers
