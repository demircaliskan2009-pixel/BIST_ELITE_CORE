from __future__ import annotations

from dataclasses import replace

import pytest

import crypto_core.service.sleeve_portfolio as portfolio
import crypto_core.validation as validation
from crypto_core.service.sleeve_portfolio_controller import SleevePortfolioController

_DAY_NS = 86_400 * 1_000_000_000
_EDGE_ID = "edge-20m"
_OTHER_EDGE_ID = "edge-20m-other"
_SLEEVE_ID = "sleeve-20m"
_RECORD_ID = "record-20m"


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
        pbo_allocation_cap=0.5,
        rejection_reasons=(),
        missing_stages=(),
    )


def _baseline(*, edge_id: str = _EDGE_ID) -> validation.Stage4BacktestBaseline:
    return validation.Stage4BacktestBaseline(
        baseline_id="baseline-20m",
        edge_id=edge_id,
        as_of_ns=31 * _DAY_NS,
        backtest_sharpe=2.0,
        backtest_hit_rate=0.60,
        backtest_slippage_bps=4.0,
        backtest_fill_rate=0.98,
        source_window_ids=("wf-20m",),
    )


def _paper_summary(*, edge_id: str = _EDGE_ID, passed: bool = True) -> validation.Stage4PaperSummary:
    return validation.Stage4PaperSummary(
        paper_id="paper-20m-pass" if passed else "paper-20m-fail",
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
    include_baseline: bool = True,
) -> portfolio.CryptoSleeveState:
    resolved_stage4 = _stage4_pass() if stage4_result == "PASS_DEFAULT" else stage4_result
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
            ("campaign-20m",),
        ),
        promotion_support=portfolio.SleevePromotionSupportResult(
            portfolio.SleevePromotionSupportStatus.SUPPORTIVE,
            True,
            portfolio.SleeveCampaignEvidenceStatus.CAMPAIGN_SUPPORTED,
            portfolio.SleeveQualificationStatus.PAPER_QUALIFIED,
            portfolio.SleeveRecommendationStatus.RECOMMENDED_ACTIVE,
        ),
        validation_pipeline_result=_pipeline_ready(),
        stage4_backtest_baseline=_baseline() if include_baseline else None,
        stage4_comparison_result=resolved_stage4,
    )


def _controller(sleeve: portfolio.CryptoSleeveState) -> SleevePortfolioController:
    return SleevePortfolioController(defined_sleeves=(sleeve,), created_at_ns=1)


def _target(snapshot: portfolio.SleevePortfolioSnapshot) -> portfolio.CryptoSleeveState:
    return next(sleeve for sleeve in snapshot.sleeves if sleeve.sleeve_id == _SLEEVE_ID)


def _approval() -> portfolio.Stage5OperatorApprovalEvidence:
    return portfolio.Stage5OperatorApprovalEvidence(
        approved=True,
        approver_id="ops-20m",
        approved_at_ns=90 * _DAY_NS,
        approval_reference="approval-20m",
        rejection_reasons=(),
    )


def _credentials() -> portfolio.Stage5CredentialAttestationEvidence:
    return portfolio.Stage5CredentialAttestationEvidence(
        live_api_credentials_valid=True,
        attested_by="security-20m",
        attested_at_ns=91 * _DAY_NS,
        attestation_reference="credentials-20m",
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


def _canary() -> portfolio.Stage5CanaryTierEvidence:
    return portfolio.Stage5CanaryTierEvidence(
        allocation_tier_pct=10.0,
        weeks_at_tier=0,
        canary_observation_count=20,
        canary_pnl_non_negative=True,
        canary_drawdown_within_limit=True,
        canary_slippage_within_limit=True,
        canary_incidents=0,
        as_of_ns=100 * _DAY_NS,
        rejection_reasons=(),
    )


def _record() -> portfolio.Stage5RuntimeEvidenceRecord:
    bundle = portfolio.Stage5RuntimeEvidenceBundle(
        edge_id=_EDGE_ID,
        as_of_ns=100 * _DAY_NS,
        operator_approval=_approval(),
        credential_attestation=_credentials(),
        risk_governance=_risk(),
        canary_tier=_canary(),
        rejection_reasons=(),
    )
    return portfolio.Stage5RuntimeEvidenceRecord(
        record_id=_RECORD_ID,
        sleeve_id=_SLEEVE_ID,
        edge_id=_EDGE_ID,
        evidence_bundle=bundle,
        created_at_ns=100 * _DAY_NS,
    )


def test_manual_stage5_gate_missing_stage4_is_attached_but_failed():
    updated = portfolio.build_sleeve_with_stage5_live_readiness_gate(
        _sleeve(stage4_result=None, include_baseline=False),
        _gate(),
    )

    assert updated.stage5_entry_gate is not None
    assert updated.stage5_entry_gate.passed is False
    assert updated.stage5_entry_gate.stage4_passed is False
    assert "stage5:stage4_comparison_missing" in updated.stage5_entry_gate.rejection_reasons
    assert "stage5:stage4_not_passed" not in updated.stage5_entry_gate.rejection_reasons
    assert portfolio.stage5_live_ready(updated.stage5_entry_gate) is False


def test_manual_stage5_gate_missing_stage4_decision_pack_blocks_live_ready():
    controller = _controller(_sleeve(stage4_result=None, include_baseline=False))

    snapshot = controller.apply_stage5_live_readiness_gate(_SLEEVE_ID, _gate())
    target = _target(snapshot)

    assert target.decision_pack.stage5_live_ready is False
    assert "stage5:stage4_comparison_missing" in target.decision_pack.stage5_live_readiness_blockers


def test_manual_stage5_gate_failed_stage4_is_attached_but_failed():
    updated = portfolio.build_sleeve_with_stage5_live_readiness_gate(
        _sleeve(stage4_result=_stage4_fail()),
        _gate(),
    )

    assert updated.stage5_entry_gate is not None
    assert updated.stage5_entry_gate.passed is False
    assert updated.stage5_entry_gate.stage4_passed is False
    assert "stage5:stage4_not_passed" in updated.stage5_entry_gate.rejection_reasons
    assert "stage5:stage4_comparison_missing" not in updated.stage5_entry_gate.rejection_reasons


def test_manual_stage5_gate_passing_stage4_preserves_passing_gate():
    gate = _gate()

    updated = portfolio.build_sleeve_with_stage5_live_readiness_gate(_sleeve(), gate)

    assert updated.stage5_entry_gate == gate
    assert portfolio.stage5_live_ready(updated.stage5_entry_gate) is True


def test_manual_stage5_gate_passing_stage4_does_not_promote_failed_gate():
    gate = _gate(
        operator_approval_recorded=False,
        rejection_reasons=("stage5:operator_approval_missing",),
    )

    updated = portfolio.build_sleeve_with_stage5_live_readiness_gate(_sleeve(), gate)

    assert updated.stage5_entry_gate is not None
    assert updated.stage5_entry_gate.passed is False
    assert "stage5:operator_approval_missing" in updated.stage5_entry_gate.rejection_reasons


def test_manual_stage5_gate_edge_id_mismatch_still_raises_when_stage4_present():
    with pytest.raises(ValueError, match="stage5 gate edge_id does not match sleeve Stage4 evidence"):
        portfolio.build_sleeve_with_stage5_live_readiness_gate(
            _sleeve(stage4_result=_stage4_pass(edge_id=_EDGE_ID)),
            _gate(edge_id=_OTHER_EDGE_ID),
        )


def test_manual_stage5_gate_clear_none_does_not_require_stage4():
    sleeve = replace(
        _sleeve(stage4_result=None, include_baseline=False),
        stage5_entry_gate=_gate(),
    )

    updated = portfolio.build_sleeve_with_stage5_live_readiness_gate(sleeve, None)

    assert updated.stage5_entry_gate is None


def test_manual_stage5_gate_normalization_is_deterministic():
    sleeve = _sleeve(stage4_result=None, include_baseline=False)
    gate = _gate(rejection_reasons=("stage5:operator_approval_missing",))

    first = portfolio.build_sleeve_with_stage5_live_readiness_gate(sleeve, gate)
    second = portfolio.build_sleeve_with_stage5_live_readiness_gate(sleeve, gate)

    assert portfolio.crypto_sleeve_state_to_dict(first) == portfolio.crypto_sleeve_state_to_dict(second)


def test_runtime_evidence_record_path_still_passes_when_stage4_passes():
    gate = portfolio.build_stage5_gate_from_runtime_evidence_record(
        _record(),
        allocation_tier_pct=10.0,
        weeks_at_tier=0,
        stage4_comparison_result=_stage4_pass(),
    )

    updated = portfolio.build_sleeve_with_stage5_live_readiness_gate(_sleeve(), gate)

    assert updated.stage5_entry_gate is not None
    assert portfolio.stage5_live_ready(updated.stage5_entry_gate) is True


def test_runtime_evidence_record_path_still_fails_when_stage4_missing():
    gate = portfolio.build_stage5_gate_from_runtime_evidence_record(
        _record(),
        allocation_tier_pct=10.0,
        weeks_at_tier=0,
        stage4_comparison_result=None,
    )

    updated = portfolio.build_sleeve_with_stage5_live_readiness_gate(
        _sleeve(stage4_result=None, include_baseline=False),
        gate,
    )

    assert updated.stage5_entry_gate is not None
    assert portfolio.stage5_live_ready(updated.stage5_entry_gate) is False
    assert "stage5:stage4_comparison_missing" in updated.stage5_entry_gate.rejection_reasons
