"""Phase 20G — Stage4/Stage5 live-readiness integration coverage hardening.

Covers the low-severity gaps identified in Phase 20F:
1. Full orchestrator Stage5 demotion path (operator_snapshot → decision_pack).
2. Backward compatibility: SleeveDecisionPackResult without stage5 fields.
3. Backward compatibility: OperatorDecisionPack without stage5 fields.
4. Stage4 + Stage5 combined blocking in a single sleeve.
5. Forbidden credential/network-key rejection via build_paper_data_source_batch_result.
6. Stage5 edge-id mismatch raises ValueError.

HARD CONSTRAINTS (verified throughout):
- No live adapter, no exchange client, no order submission.
- No env var or credential reads.
- No allocation mutation.
- No production behavior change.
"""

from __future__ import annotations

import json
from dataclasses import replace
from unittest.mock import MagicMock

import pytest

import crypto_core.service.sleeve_portfolio as portfolio
import crypto_core.validation as validation
from crypto_core.service.artifact_export import (
    OperatorDecisionPack,
    decision_pack_from_dict,
    decision_pack_to_dict,
)
from crypto_core.service.models import (
    ExecutionIntelligenceStatus,
    QueuePressure,
    QueueSnapshot,
    ServiceStatus,
    WatchdogStatus,
)
from crypto_core.service.paper_shadow_session_controller import (
    PaperShadowSessionCorruptError,
    build_paper_data_source_batch_result,
)
from crypto_core.service.service_orchestrator import ServiceOrchestrator

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

_DAY_NS = 86_400 * 1_000_000_000
_EDGE_ID = "edge-20g"
_SLEEVE_ID = "sleeve-20g"


# ---------------------------------------------------------------------------
# Stubs
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


class _ReviewStatus:
    value = "active"


class _Review:
    campaign_count = 1
    final_report = None
    is_finalized = False
    review_id = "review-20g"
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


class _ReviewSnapshot:
    updated_at_ns: int = 303
    provisional_verdict: str = "promote"
    provisional_summary: str = "Promotion review supports candidate."
    insufficient_evidence: tuple[str, ...] = ()
    is_ready_to_finalize: bool = True
    campaign_ids: tuple[str, ...] = ("campaign-20g",)
    campaign_count: int = 1
    ext_regime_quality: str = "supportive"
    ext_regime_governance: dict = {}
    verdict_distribution: dict = {}
    execution_sufficiency: dict = {}
    symbol_breadth: dict = {}


# ---------------------------------------------------------------------------
# Fixture helpers
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


def _baseline(*, edge_id: str = _EDGE_ID) -> validation.Stage4BacktestBaseline:
    return validation.Stage4BacktestBaseline(
        baseline_id="baseline-20g",
        edge_id=edge_id,
        as_of_ns=31 * _DAY_NS,
        backtest_sharpe=2.0,
        backtest_hit_rate=0.60,
        backtest_slippage_bps=4.0,
        backtest_fill_rate=0.98,
        source_window_ids=("wf-001", "wf-002"),
    )


def _paper_summary(*, edge_id: str = _EDGE_ID) -> validation.Stage4PaperSummary:
    return validation.Stage4PaperSummary(
        paper_id="paper-20g",
        edge_id=edge_id,
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
    """Build a Stage5 gate; all fields passing by default."""
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
    stage4_result: validation.Stage4ComparisonResult | None = None,
    validation_pipeline: validation.ValidationPipelineResult | None = None,
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
            ("campaign-20g",),
        ),
        promotion_support=portfolio.SleevePromotionSupportResult(
            portfolio.SleevePromotionSupportStatus.SUPPORTIVE,
            True,
            portfolio.SleeveCampaignEvidenceStatus.CAMPAIGN_SUPPORTED,
            portfolio.SleeveQualificationStatus.PAPER_QUALIFIED,
            portfolio.SleeveRecommendationStatus.RECOMMENDED_ACTIVE,
        ),
        validation_pipeline_result=validation_pipeline if validation_pipeline is not None else _pipeline_ready(),
        stage4_backtest_baseline=_baseline(),
        stage4_comparison_result=stage4_result if stage4_result is not None else _stage4_pass(),
        stage5_entry_gate=stage5_gate,
    )


def _orchestrator(sleeve: portfolio.CryptoSleeveState) -> ServiceOrchestrator:
    orch = ServiceOrchestrator(
        service=_Service(),
        readiness_level="paper_live",
        sleeves=(sleeve,),
    )
    orch._decision_pack_readiness_status = MagicMock(return_value=None)  # type: ignore[method-assign]
    orch._review = _Review()  # type: ignore[assignment]
    return orch


def _old_decision_pack_payload() -> dict:
    """Minimal OperatorDecisionPack payload from before Stage5 fields existed."""
    return {
        "artifact_time_ns": 1000,
        "review_id": "review-old",
        "review_timestamp_ns": 1000,
        "review_status": "active",
        "promotion_verdict": "promote",
        "operator_disposition": "approve",
        "decision_summary": "Legacy payload.",
        "readiness_level": "paper_live",
        "readiness_is_supportive": True,
        "criteria_summary": {},
        "insufficient_evidence_summary": {},
        "external_regime_quality": "supportive",
        "external_regime_evidence_available": False,
        "external_regime_evidence_sufficient": True,
        "external_regime_governance": {},
        "external_regime_summary": "OK",
        "campaign_coverage": {},
        "reason_codes": {},
        # stage5_live_ready, stage5_live_ready_sleeve_ids, stage5_live_readiness_blockers intentionally absent
    }


def _old_sleeve_decision_pack_payload() -> dict:
    """Minimal SleeveDecisionPackResult payload from before Stage5 fields existed."""
    return {
        "status": "recommended_active",
        "recommended_active": True,
        "currently_eligible": True,
        "promotion_candidate": True,
        "strongly_supported_candidate": False,
        "recommendation_status": "recommended_active",
        "qualification_status": "paper_qualified",
        "campaign_evidence_status": "campaign_supported",
        "promotion_support_status": "supportive",
        "promotion_candidate_status": "supported",
        "missing_evidence": [],
        "blocking_reasons": [],
        "reason_summary": "",
        "next_step": "Admit to paper.",
        # stage5_live_ready and stage5_live_readiness_blockers intentionally absent
    }


# ---------------------------------------------------------------------------
# Gap 1: Full orchestrator Stage5 demotion path
# ---------------------------------------------------------------------------


def test_orchestrator_failed_stage5_blocking_reason_in_decision_pack_via_combined_status():
    """Stage5 blocking reason must be in decision_pack.blocking_reasons through combined_status_dict path."""
    # Use pre-loaded gate (like Phase 20D) to get full path coverage.
    sleeve = _sleeve(stage5_gate=_stage5_gate(operator_approval_recorded=False))
    orch = _orchestrator(sleeve)

    status = orch.combined_status_dict()
    sleeve_status = status["sleeve_portfolio"]["sleeves"][0]

    assert "stage5:operator_approval_missing" in sleeve_status["promotion_candidate"]["blocking_reasons"]
    assert "stage5:operator_approval_missing" in sleeve_status["decision_pack"]["blocking_reasons"]


def test_orchestrator_failed_stage5_phase20e_invariant_holds():
    """Phase 20E invariant: decision_pack.status != RECOMMENDED_ACTIVE when blocking_reasons non-empty."""
    sleeve = _sleeve()
    orch = _orchestrator(sleeve)

    failed_gate = _stage5_gate(kill_switch_clear=False)
    snap = orch.apply_stage5_live_readiness_gate_to_sleeve(_SLEEVE_ID, failed_gate)

    sleeve_snap = snap.sleeve_portfolio.sleeves[0]
    assert sleeve_snap.decision_pack is not None
    # Core invariant: RECOMMENDED_ACTIVE must never coexist with non-empty blocking_reasons.
    if sleeve_snap.decision_pack.blocking_reasons:
        assert sleeve_snap.decision_pack.status != portfolio.SleeveDecisionPackStatus.RECOMMENDED_ACTIVE


def test_orchestrator_failed_stage5_blocking_reason_in_decision_pack_via_snapshot():
    """Failed Stage5 gate applied via apply_stage5_live_readiness_gate_to_sleeve propagates to decision_pack."""
    sleeve = _sleeve()
    orch = _orchestrator(sleeve)

    failed_gate = _stage5_gate(kill_switch_clear=False)
    snap = orch.apply_stage5_live_readiness_gate_to_sleeve(_SLEEVE_ID, failed_gate)

    sleeve_snap = snap.sleeve_portfolio.sleeves[0]
    assert any(r.startswith("stage5:") for r in sleeve_snap.decision_pack.blocking_reasons)


def test_orchestrator_combined_status_dict_is_json_serializable():
    """combined_status_dict() must be fully JSON-serializable after Stage5 gate applied."""
    sleeve = _sleeve()
    orch = _orchestrator(sleeve)

    failed_gate = _stage5_gate(operator_approval_recorded=False)
    orch.apply_stage5_live_readiness_gate_to_sleeve(_SLEEVE_ID, failed_gate)

    status = orch.combined_status_dict()
    # Must not raise — all values must be JSON-safe.
    serialized = json.dumps(status)
    assert len(serialized) > 0


def test_orchestrator_decision_pack_stage5_blockers_propagate():
    """decision_pack().stage5_live_readiness_blockers must include Stage5 reason."""
    sleeve = _sleeve()
    orch = _orchestrator(sleeve)

    failed_gate = _stage5_gate(risk_governance_clear=False)
    orch.apply_stage5_live_readiness_gate_to_sleeve(_SLEEVE_ID, failed_gate)

    pack = orch.decision_pack()
    assert "stage5:risk_governance_not_clear" in pack.stage5_live_readiness_blockers


def test_orchestrator_decision_pack_stage5_live_ready_false_on_failed_gate():
    """decision_pack().stage5_live_ready must be False when any sleeve fails Stage5."""
    sleeve = _sleeve()
    orch = _orchestrator(sleeve)

    failed_gate = _stage5_gate(operator_approval_recorded=False)
    orch.apply_stage5_live_readiness_gate_to_sleeve(_SLEEVE_ID, failed_gate)

    pack = orch.decision_pack()
    assert pack.stage5_live_ready is False


def test_orchestrator_missing_stage5_gate_no_stage5_blocking_reasons():
    """No Stage5 gate applied → no stage5: codes in decision_pack.blocking_reasons."""
    sleeve = _sleeve(stage5_gate=None)
    orch = _orchestrator(sleeve)

    status = orch.combined_status_dict()
    sleeve_status = status["sleeve_portfolio"]["sleeves"][0]

    stage5_in_dp = [r for r in sleeve_status["decision_pack"]["blocking_reasons"] if r.startswith("stage5:")]
    assert stage5_in_dp == [], f"Expected no stage5 codes, got: {stage5_in_dp}"


# ---------------------------------------------------------------------------
# Gap 2: Backward compatibility — SleeveDecisionPackResult without stage5 fields
# ---------------------------------------------------------------------------


def test_sleeve_decision_pack_from_dict_missing_stage5_fields_defaults_safely():
    """Old payload without stage5 fields must deserialize with safe defaults."""
    payload = _old_sleeve_decision_pack_payload()
    # Confirm these keys are absent in the old payload
    assert "stage5_live_ready" not in payload
    assert "stage5_live_readiness_blockers" not in payload

    result = portfolio.sleeve_decision_pack_result_from_dict(payload)

    assert result.stage5_live_ready is False
    assert result.stage5_live_readiness_blockers == ()


def test_sleeve_decision_pack_from_dict_missing_stage5_fields_not_live_ready():
    """Old payload deserialized → must be fail-closed: stage5_live_ready=False."""
    result = portfolio.sleeve_decision_pack_result_from_dict(_old_sleeve_decision_pack_payload())
    assert result.stage5_live_ready is False


def test_sleeve_decision_pack_from_dict_stage5_fields_present_roundtrip():
    """If stage5 fields are present in payload, they must survive deserialization faithfully."""
    payload = _old_sleeve_decision_pack_payload()
    payload["stage5_live_ready"] = False
    payload["stage5_live_readiness_blockers"] = ["stage5:operator_approval_missing"]

    result = portfolio.sleeve_decision_pack_result_from_dict(payload)

    assert result.stage5_live_ready is False
    assert "stage5:operator_approval_missing" in result.stage5_live_readiness_blockers


# ---------------------------------------------------------------------------
# Gap 3: Backward compatibility — OperatorDecisionPack without stage5 fields
# ---------------------------------------------------------------------------


def test_operator_decision_pack_from_dict_missing_stage5_fields_defaults_safely():
    """Old OperatorDecisionPack payload without stage5 fields must deserialize with safe defaults."""
    payload = _old_decision_pack_payload()
    assert "stage5_live_ready" not in payload
    assert "stage5_live_ready_sleeve_ids" not in payload
    assert "stage5_live_readiness_blockers" not in payload

    result = decision_pack_from_dict(payload)

    assert result.stage5_live_ready is False
    assert result.stage5_live_ready_sleeve_ids == ()
    assert result.stage5_live_readiness_blockers == ()


def test_operator_decision_pack_from_dict_stage5_false_is_fail_closed():
    """Old payload defaults must be fail-closed: stage5_live_ready=False."""
    result = decision_pack_from_dict(_old_decision_pack_payload())
    assert result.stage5_live_ready is False


def test_operator_decision_pack_roundtrip_with_stage5_fields():
    """OperatorDecisionPack with stage5 fields must survive to_dict → from_dict roundtrip."""
    pack = OperatorDecisionPack(
        artifact_time_ns=1000,
        review_id="review-rt",
        review_timestamp_ns=1000,
        review_status="active",
        promotion_verdict="promote",
        operator_disposition="approve",
        decision_summary="Roundtrip test.",
        readiness_level="paper_live",
        readiness_is_supportive=True,
        external_regime_quality="supportive",
        external_regime_evidence_available=False,
        external_regime_evidence_sufficient=True,
        external_regime_governance={},
        external_regime_summary="OK",
        campaign_coverage={},
        reason_codes={},
        insufficient_evidence_summary={},
        stage5_live_ready=False,
        stage5_live_ready_sleeve_ids=(),
        stage5_live_readiness_blockers=("stage5:operator_approval_missing",),
    )
    d = decision_pack_to_dict(pack)
    recovered = decision_pack_from_dict(d)

    assert recovered.stage5_live_ready is False
    assert recovered.stage5_live_ready_sleeve_ids == ()
    assert "stage5:operator_approval_missing" in recovered.stage5_live_readiness_blockers


def test_operator_decision_pack_roundtrip_json_safe():
    """decision_pack_to_dict output must be JSON-serializable."""
    pack = OperatorDecisionPack(
        artifact_time_ns=1000,
        review_id="review-json",
        review_timestamp_ns=1000,
        review_status="active",
        promotion_verdict="promote",
        operator_disposition="approve",
        decision_summary="JSON safe.",
        readiness_level="paper_live",
        readiness_is_supportive=True,
        external_regime_quality="supportive",
        external_regime_evidence_available=False,
        external_regime_evidence_sufficient=True,
        external_regime_governance={},
        external_regime_summary="OK",
        campaign_coverage={},
        reason_codes={},
        insufficient_evidence_summary={},
    )
    d = decision_pack_to_dict(pack)
    serialized = json.dumps(d)
    assert len(serialized) > 0


# ---------------------------------------------------------------------------
# Gap 4: Stage4 + Stage5 combined blocking
# ---------------------------------------------------------------------------


def test_stage4_and_stage5_combined_blocking_both_present():
    """Sleeve with missing Stage4 evidence AND failed Stage5 gate: correct field placement.

    Design: Stage4 missing evidence → decision_pack.missing_evidence (not blocking_reasons).
            Stage5 gate failure → decision_pack.blocking_reasons.
            Phase 20E guard: RECOMMENDED_ACTIVE + non-empty blocking_reasons → BLOCKED.
    """
    # Build a Stage4 failure: result=None but validation_ready=True forces required=True
    stage_status = validation.ValidationPipelineStageStatus(
        stage="stage",
        ran=True,
        passed=True,
        skipped=False,
        rejection_reasons=(),
    )
    pipeline_ready = validation.ValidationPipelineResult(
        validation_ready=True,
        stage2_status=replace(stage_status, stage="stage2_walk_forward"),
        pbo_status=replace(stage_status, stage="pbo"),
        stage3_status=replace(stage_status, stage="stage3_stress"),
        pbo_allocation_cap=None,
        rejection_reasons=(),
        missing_stages=(),
    )
    # stage4_comparison_result=None + validation_pipeline_result.validation_ready=True
    # → _stage4_effectively_required=True → stage4:comparison_missing in missing_evidence
    failed_gate = _stage5_gate(operator_approval_recorded=False)

    sleeve_no_stage4 = portfolio.CryptoSleeveState(
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
            ("campaign-20g",),
        ),
        promotion_support=portfolio.SleevePromotionSupportResult(
            portfolio.SleevePromotionSupportStatus.SUPPORTIVE,
            True,
            portfolio.SleeveCampaignEvidenceStatus.CAMPAIGN_SUPPORTED,
            portfolio.SleeveQualificationStatus.PAPER_QUALIFIED,
            portfolio.SleeveRecommendationStatus.RECOMMENDED_ACTIVE,
        ),
        validation_pipeline_result=pipeline_ready,
        stage4_backtest_baseline=_baseline(),
        stage4_comparison_result=None,  # Missing Stage4 result
        stage5_entry_gate=failed_gate,
    )

    promotion_candidate = portfolio._build_sleeve_promotion_candidate_result(sleeve_no_stage4)  # type: ignore[attr-defined]
    enriched = replace(sleeve_no_stage4, promotion_candidate=promotion_candidate)
    result = portfolio._build_sleeve_decision_pack_result(enriched)  # type: ignore[attr-defined]

    # Stage4 missing evidence → missing_evidence field (evidence gap, not a blocker)
    assert "stage4:comparison_missing" in result.missing_evidence, (
        f"Expected stage4:comparison_missing in missing_evidence, got: {result.missing_evidence}"
    )
    # Stage5 gate failure → blocking_reasons field
    stage5_reasons = [r for r in result.blocking_reasons if r.startswith("stage5:")]
    assert len(stage5_reasons) >= 1, f"Expected stage5 reason in blocking_reasons, got: {result.blocking_reasons}"
    # Phase 20E guard: RECOMMENDED_ACTIVE + blocking_reasons → demoted to BLOCKED
    assert result.status == portfolio.SleeveDecisionPackStatus.BLOCKED


def test_stage4_stage5_combined_blocking_deterministic():
    """Stage4+Stage5 combined blocking must produce identical output on repeated calls."""
    stage_status = validation.ValidationPipelineStageStatus(
        stage="stage",
        ran=True,
        passed=True,
        skipped=False,
        rejection_reasons=(),
    )
    pipeline_ready = validation.ValidationPipelineResult(
        validation_ready=True,
        stage2_status=replace(stage_status, stage="stage2_walk_forward"),
        pbo_status=replace(stage_status, stage="pbo"),
        stage3_status=replace(stage_status, stage="stage3_stress"),
        pbo_allocation_cap=None,
        rejection_reasons=(),
        missing_stages=(),
    )
    failed_gate = _stage5_gate(kill_switch_clear=False)

    sleeve = portfolio.CryptoSleeveState(
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
            ("campaign-20g",),
        ),
        promotion_support=portfolio.SleevePromotionSupportResult(
            portfolio.SleevePromotionSupportStatus.SUPPORTIVE,
            True,
            portfolio.SleeveCampaignEvidenceStatus.CAMPAIGN_SUPPORTED,
            portfolio.SleeveQualificationStatus.PAPER_QUALIFIED,
            portfolio.SleeveRecommendationStatus.RECOMMENDED_ACTIVE,
        ),
        validation_pipeline_result=pipeline_ready,
        stage4_backtest_baseline=_baseline(),
        stage4_comparison_result=None,
        stage5_entry_gate=failed_gate,
    )

    def _build(s: portfolio.CryptoSleeveState) -> portfolio.SleeveDecisionPackResult:
        cand = portfolio._build_sleeve_promotion_candidate_result(s)  # type: ignore[attr-defined]
        enriched = replace(s, promotion_candidate=cand)
        return portfolio._build_sleeve_decision_pack_result(enriched)  # type: ignore[attr-defined]

    result_a = _build(sleeve)
    result_b = _build(sleeve)

    assert result_a.status == result_b.status
    assert result_a.blocking_reasons == result_b.blocking_reasons


# ---------------------------------------------------------------------------
# Gap 5: Forbidden credential/network key rejection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "forbidden_key",
    ["api_key", "secret", "token", "client", "network_client", "password", "private_key", "credentials"],
)
def test_paper_data_source_batch_rejects_forbidden_top_level_key(forbidden_key: str):
    """build_paper_data_source_batch_result must raise on any forbidden credential/network key."""
    payload = {
        "source_id": "src-20g",
        "source_type": "live_feed",
        "venue": "binance",
        "as_of_ns": 31 * _DAY_NS,
        "records": [
            {
                "symbol": "BTCUSDT",
                "timestamp_ns": 31 * _DAY_NS,
                "open": 50000.0,
                "high": 50100.0,
                "low": 49900.0,
                "close": 50050.0,
                "volume": 1.5,
            }
        ],
        forbidden_key: "THIS_MUST_BE_REJECTED",
    }
    with pytest.raises(PaperShadowSessionCorruptError):
        build_paper_data_source_batch_result(
            payload,
            allowed_source_ids=("src-20g",),
            allow_unknown_source=False,
        )


@pytest.mark.parametrize(
    "forbidden_key",
    ["api_key", "secret", "token", "client", "network_client"],
)
def test_paper_data_source_batch_rejects_forbidden_nested_key(forbidden_key: str):
    """Forbidden keys nested inside records must also raise PaperShadowSessionCorruptError."""
    payload = {
        "source_id": "src-20g-nested",
        "source_type": "live_feed",
        "venue": "binance",
        "as_of_ns": 31 * _DAY_NS,
        "records": [
            {
                "symbol": "BTCUSDT",
                "timestamp_ns": 31 * _DAY_NS,
                "open": 50000.0,
                "high": 50100.0,
                "low": 49900.0,
                "close": 50050.0,
                "volume": 1.5,
                forbidden_key: "SHOULD_FAIL",
            }
        ],
    }
    with pytest.raises(PaperShadowSessionCorruptError):
        build_paper_data_source_batch_result(
            payload,
            allowed_source_ids=("src-20g-nested",),
            allow_unknown_source=False,
        )


# ---------------------------------------------------------------------------
# Gap 6: Stage5 edge-id mismatch
# ---------------------------------------------------------------------------


def test_build_sleeve_with_stage5_gate_edge_id_mismatch_raises():
    """Gate edge_id != sleeve Stage4 evidence edge_id must raise ValueError."""
    sleeve = _sleeve()
    gate = _stage5_gate(edge_id="totally-different-edge")

    with pytest.raises(ValueError, match="stage5 gate edge_id does not match"):
        portfolio.build_sleeve_with_stage5_live_readiness_gate(sleeve, gate)


def test_build_sleeve_with_stage5_gate_matching_edge_id_accepted():
    """Gate with matching edge_id must be accepted without error."""
    sleeve = _sleeve()
    gate = _stage5_gate(edge_id=_EDGE_ID)

    result = portfolio.build_sleeve_with_stage5_live_readiness_gate(sleeve, gate)

    assert result.stage5_entry_gate is gate


def test_build_sleeve_with_stage5_gate_none_clears_gate():
    """Passing gate=None must clear any existing Stage5 gate."""
    sleeve = _sleeve(stage5_gate=_stage5_gate())
    assert sleeve.stage5_entry_gate is not None

    result = portfolio.build_sleeve_with_stage5_live_readiness_gate(sleeve, None)

    assert result.stage5_entry_gate is None


def test_build_sleeve_with_stage5_gate_mismatch_message_is_stable():
    """ValueError message must be stable across identical calls (determinism)."""
    sleeve = _sleeve()
    gate = _stage5_gate(edge_id="wrong-edge-stable")

    msgs = []
    for _ in range(3):
        with pytest.raises(ValueError) as exc_info:
            portfolio.build_sleeve_with_stage5_live_readiness_gate(sleeve, gate)
        msgs.append(str(exc_info.value))

    assert len(set(msgs)) == 1, "ValueError message must be deterministic"
