from __future__ import annotations

from dataclasses import replace

import crypto_core.validation as validation
from crypto_core.service import sleeve_portfolio as portfolio

_DAY_NS = 86400 * 1_000_000_000


def _baseline() -> validation.Stage4BacktestBaseline:
    return validation.build_stage4_backtest_baseline(
        baseline_id="baseline-001",
        edge_id="edge-alpha",
        as_of_ns=31 * _DAY_NS,
        backtest_sharpe=2.0,
        backtest_hit_rate=0.60,
        backtest_slippage_bps=5.0,
        backtest_fill_rate=0.95,
        source_window_ids=("wf-001", "wf-002"),
    )


def _paper(**overrides: float | int | str | None) -> validation.Stage4PaperSummary:
    values = {
        "paper_id": "paper-001",
        "edge_id": "edge-alpha",
        "started_at_ns": 1,
        "stopped_at_ns": 31 * _DAY_NS + 1,
        "paper_sharpe": 1.2,
        "paper_hit_rate": 0.58,
        "paper_slippage_bps": 4.0,
        "paper_fill_rate": 0.97,
        "paper_trade_count": 42,
    }
    values.update(overrides)
    return validation.Stage4PaperSummary(**values)


def _pipeline(*, ready: bool) -> validation.ValidationPipelineResult:
    stage = validation.ValidationPipelineStageStatus(
        stage="stage",
        ran=True,
        passed=ready,
        skipped=False,
        rejection_reasons=(),
    )
    return validation.ValidationPipelineResult(
        validation_ready=ready,
        stage2_status=replace(stage, stage="stage2_walk_forward"),
        pbo_status=replace(stage, stage="pbo"),
        stage3_status=replace(stage, stage="stage3_stress"),
        pbo_allocation_cap=None,
        rejection_reasons=(),
        missing_stages=() if ready else ("stage2_walk_forward",),
    )


def _sleeve(
    *,
    stage4_result: validation.Stage4ComparisonResult | None = None,
    stage4_required: bool = False,
    validation_pipeline_result: validation.ValidationPipelineResult | None = None,
) -> portfolio.CryptoSleeveState:
    return portfolio.CryptoSleeveState(
        sleeve_id="sleeve-microstructure",
        sleeve_type=portfolio.CryptoSleeveType.MICROSTRUCTURE,
        status=portfolio.CryptoSleeveStatus.DEFINED,
        validation_pipeline_result=validation_pipeline_result,
        stage4_comparison_result=stage4_result,
        stage4_comparison_required=stage4_required,
    )


def _roundtrip(sleeve: portfolio.CryptoSleeveState) -> portfolio.CryptoSleeveState:
    return portfolio.crypto_sleeve_state_from_dict(portfolio.crypto_sleeve_state_to_dict(sleeve))


def test_build_sleeve_with_stage4_comparison_pass():
    sleeve = portfolio.build_sleeve_with_stage4_comparison(_sleeve(), _baseline(), _paper())
    result = sleeve.stage4_comparison_result
    assert result is not None
    assert result.status == "PASS"
    assert result.passed is True
    assert result.rejection_reasons == ()


def test_build_sleeve_with_stage4_comparison_reject_duration():
    sleeve = portfolio.build_sleeve_with_stage4_comparison(
        _sleeve(),
        _baseline(),
        _paper(stopped_at_ns=29 * _DAY_NS + 1),
    )
    result = sleeve.stage4_comparison_result
    assert result is not None
    assert result.status == "REJECT"
    assert "stage4:duration_below_minimum" in result.rejection_reasons


def test_build_sleeve_with_stage4_comparison_none_baseline():
    sleeve = portfolio.build_sleeve_with_stage4_comparison(_sleeve(), None, _paper())
    result = sleeve.stage4_comparison_result
    assert result is not None
    assert result.status == "INSUFFICIENT_EVIDENCE"
    assert "stage4:backtest_baseline_missing" in result.rejection_reasons


def test_build_sleeve_with_stage4_comparison_none_paper():
    sleeve = portfolio.build_sleeve_with_stage4_comparison(_sleeve(), _baseline(), None)
    result = sleeve.stage4_comparison_result
    assert result is not None
    assert result.status == "INSUFFICIENT_EVIDENCE"
    assert "stage4:paper_summary_missing" in result.rejection_reasons


def test_stage4_comparison_result_from_dict_roundtrip_pass():
    result = validation.compare_stage4(_baseline(), _paper())
    restored = validation.stage4_comparison_result_from_dict(validation.stage4_comparison_result_to_dict(result))
    assert restored == result
    assert restored.baseline_id == "baseline-001"
    assert restored.paper_id == "paper-001"
    assert restored.edge_id == "edge-alpha"
    assert restored.required_min_paper_sharpe == 1.0


def test_stage4_comparison_result_from_dict_roundtrip_reject_reasons():
    result = validation.compare_stage4(_baseline(), _paper(stopped_at_ns=29 * _DAY_NS + 1))
    restored = validation.stage4_comparison_result_from_dict(validation.stage4_comparison_result_to_dict(result))
    assert restored.status == "REJECT"
    assert restored.rejection_reasons == ("stage4:duration_below_minimum",)


def test_sleeve_with_stage4_pass_survives_state_dict_roundtrip():
    result = validation.compare_stage4(_baseline(), _paper())
    restored = _roundtrip(_sleeve(stage4_result=result))
    assert restored.stage4_comparison_result is not None
    assert restored.stage4_comparison_result.passed is True


def test_sleeve_with_stage4_reject_survives_state_dict_roundtrip():
    result = validation.compare_stage4(_baseline(), _paper(stopped_at_ns=29 * _DAY_NS + 1))
    restored = _roundtrip(_sleeve(stage4_result=result))
    assert restored.stage4_comparison_result is not None
    assert restored.stage4_comparison_result.rejection_reasons == ("stage4:duration_below_minimum",)


def test_sleeve_with_no_stage4_survives_state_dict_roundtrip():
    restored = _roundtrip(_sleeve())
    assert restored.stage4_comparison_result is None


def test_stage4_comparison_required_explicit_true_survives_state_dict_roundtrip():
    restored = _roundtrip(_sleeve(stage4_required=True))
    assert restored.stage4_comparison_required is True


def test_effective_stage4_required_from_validation_ready_survives_state_dict_roundtrip():
    sleeve = _sleeve(
        validation_pipeline_result=_pipeline(ready=True),
        stage4_required=False,
        stage4_result=None,
    )
    restored = _roundtrip(sleeve)
    assert restored.validation_pipeline_result is None
    assert restored.stage4_comparison_required is True
    candidate = portfolio._build_sleeve_promotion_candidate_result(restored)
    assert "stage4:comparison_missing" in candidate.missing_evidence


def test_effective_required_false_when_validation_not_ready_roundtrip():
    restored = _roundtrip(
        _sleeve(
            validation_pipeline_result=_pipeline(ready=False),
            stage4_required=False,
        )
    )
    assert restored.validation_pipeline_result is None
    assert restored.stage4_comparison_required is False
