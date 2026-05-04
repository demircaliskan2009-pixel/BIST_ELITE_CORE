from __future__ import annotations

from crypto_core import validation as validation_module
from crypto_core.validation import (
    PBOValidationResult,
    StressValidationResult,
    ValidationPipelineResult,
    ValidationPipelineStageStatus,
    WalkForwardValidationResult,
    validate_pipeline,
)


def _walk_forward_result(
    *,
    supportive: bool = True,
    rejection_reasons: tuple[str, ...] = (),
) -> WalkForwardValidationResult:
    return WalkForwardValidationResult(
        supportive=supportive,
        total_window_count=3,
        valid_oos_window_count=3,
        supportive_window_count=3 if supportive else 1,
        positive_expectancy_window_count=3 if supportive else 1,
        required_positive_expectancy_window_count=2,
        drawdown_safe_window_count=3 if supportive else 1,
        positive_profit_factor_window_count=3 if supportive else 1,
        required_positive_profit_factor_window_count=2,
        rejection_reasons=rejection_reasons,
        window_results=(),
    )


def _pbo_result(
    *,
    approved: bool = True,
    pbo_action: str | None = "approved",
    allocation_cap: float | None = None,
    rejection_reasons: tuple[str, ...] = (),
) -> PBOValidationResult:
    return PBOValidationResult(
        approved=approved,
        pbo_value=0.10 if approved else 0.45,
        pbo_action=pbo_action,
        allocation_cap=allocation_cap,
        dsr_value=1.0,
        dsr_passed=True,
        mc_p_value=0.01,
        mc_passed=True,
        regime_pbo=(),
        sensitivity_fragile=False,
        cscv_matrix_stored=True,
        rejection_reasons=rejection_reasons,
    )


def _stress_result(
    *,
    all_passed: bool = True,
    rejection_reasons: tuple[str, ...] = (),
) -> StressValidationResult:
    return StressValidationResult(
        all_passed=all_passed,
        scenario_results=(),
        rejection_reasons=rejection_reasons,
    )


def test_all_stages_supportive_validation_ready_true():
    result = validate_pipeline(_walk_forward_result(), _pbo_result(), _stress_result())

    assert result.validation_ready is True
    assert result.stage2_status == ValidationPipelineStageStatus("stage2_walk_forward", True, True, False, ())
    assert result.pbo_status == ValidationPipelineStageStatus("pbo", True, True, False, ())
    assert result.stage3_status == ValidationPipelineStageStatus("stage3_stress", True, True, False, ())
    assert result.pbo_allocation_cap is None
    assert result.rejection_reasons == ()
    assert result.missing_stages == ()


def test_missing_walk_forward_blocks_all():
    result = validate_pipeline(None, _pbo_result(), _stress_result())

    assert result.validation_ready is False
    assert result.stage2_status == ValidationPipelineStageStatus(
        "stage2_walk_forward",
        False,
        False,
        False,
        ("stage2:stage2_missing",),
    )
    assert result.pbo_status == ValidationPipelineStageStatus("pbo", False, False, True, ())
    assert result.stage3_status == ValidationPipelineStageStatus("stage3_stress", False, False, True, ())
    assert result.rejection_reasons == ("stage2:stage2_missing",)
    assert result.missing_stages == ("stage2_walk_forward", "pbo", "stage3_stress")


def test_malformed_walk_forward_fails_closed():
    result = validate_pipeline(object(), _pbo_result(), _stress_result())

    assert result.validation_ready is False
    assert result.stage2_status.rejection_reasons == ("stage2:stage2_malformed",)
    assert result.pbo_status.skipped is True
    assert result.stage3_status.skipped is True
    assert result.rejection_reasons == ("stage2:stage2_malformed",)
    assert result.missing_stages == ("stage2_walk_forward", "pbo", "stage3_stress")


def test_walk_forward_not_supportive_blocks_pbo_and_stage3():
    result = validate_pipeline(
        _walk_forward_result(
            supportive=False,
            rejection_reasons=("insufficient_valid_oos_windows", "insufficient_positive_expectancy_windows"),
        ),
        _pbo_result(),
        _stress_result(),
    )

    assert result.validation_ready is False
    assert result.stage2_status.passed is False
    assert result.pbo_status.skipped is True
    assert result.stage3_status.skipped is True
    assert result.rejection_reasons == (
        "stage2:insufficient_valid_oos_windows",
        "stage2:insufficient_positive_expectancy_windows",
    )
    assert result.missing_stages == ("pbo", "stage3_stress")


def test_missing_pbo_blocks_stage3():
    result = validate_pipeline(_walk_forward_result(), None, _stress_result())

    assert result.validation_ready is False
    assert result.stage2_status.passed is True
    assert result.pbo_status == ValidationPipelineStageStatus("pbo", False, False, False, ("pbo:pbo_missing",))
    assert result.stage3_status == ValidationPipelineStageStatus("stage3_stress", False, False, True, ())
    assert result.rejection_reasons == ("pbo:pbo_missing",)
    assert result.missing_stages == ("pbo", "stage3_stress")


def test_malformed_pbo_fails_closed():
    result = validate_pipeline(_walk_forward_result(), object(), _stress_result())

    assert result.validation_ready is False
    assert result.pbo_status.rejection_reasons == ("pbo:pbo_malformed",)
    assert result.stage3_status.skipped is True
    assert result.rejection_reasons == ("pbo:pbo_malformed",)
    assert result.missing_stages == ("pbo", "stage3_stress")


def test_pbo_rejected_blocks_stage3():
    result = validate_pipeline(
        _walk_forward_result(),
        _pbo_result(approved=False, pbo_action="rejected", rejection_reasons=("pbo_rejected",)),
        _stress_result(),
    )

    assert result.validation_ready is False
    assert result.pbo_status.passed is False
    assert result.stage3_status.skipped is True
    assert result.rejection_reasons == ("pbo:pbo_rejected",)
    assert result.missing_stages == ("stage3_stress",)


def test_pbo_requires_additional_oos_blocks_stage3():
    result = validate_pipeline(
        _walk_forward_result(),
        _pbo_result(
            approved=False,
            pbo_action="requires_additional_oos",
            rejection_reasons=("pbo_requires_additional_oos",),
        ),
        _stress_result(),
    )

    assert result.validation_ready is False
    assert result.pbo_status.rejection_reasons == ("pbo:pbo_requires_additional_oos",)
    assert result.stage3_status.skipped is True
    assert result.rejection_reasons == ("pbo:pbo_requires_additional_oos",)


def test_pbo_approved_capped_propagates_allocation_cap_and_can_be_ready():
    result = validate_pipeline(
        _walk_forward_result(),
        _pbo_result(approved=True, pbo_action="approved_capped", allocation_cap=0.5),
        _stress_result(),
    )

    assert result.validation_ready is True
    assert result.pbo_status.passed is True
    assert result.pbo_allocation_cap == 0.5
    assert result.rejection_reasons == ()


def test_missing_stress_blocks_even_if_walk_forward_and_pbo_pass():
    result = validate_pipeline(_walk_forward_result(), _pbo_result(), None)

    assert result.validation_ready is False
    assert result.stage3_status == ValidationPipelineStageStatus(
        "stage3_stress",
        False,
        False,
        False,
        ("stage3:stage3_missing",),
    )
    assert result.rejection_reasons == ("stage3:stage3_missing",)
    assert result.missing_stages == ("stage3_stress",)


def test_malformed_stress_fails_closed():
    result = validate_pipeline(_walk_forward_result(), _pbo_result(), object())

    assert result.validation_ready is False
    assert result.stage3_status.rejection_reasons == ("stage3:stage3_malformed",)
    assert result.rejection_reasons == ("stage3:stage3_malformed",)
    assert result.missing_stages == ("stage3_stress",)


def test_stress_not_passed_blocks():
    result = validate_pipeline(
        _walk_forward_result(),
        _pbo_result(),
        _stress_result(all_passed=False, rejection_reasons=("flash_crash:negative_expectancy",)),
    )

    assert result.validation_ready is False
    assert result.stage3_status.passed is False
    assert result.rejection_reasons == ("stage3:flash_crash:negative_expectancy",)
    assert result.missing_stages == ()


def test_stage2_reasons_are_prefixed_correctly():
    result = validate_pipeline(
        _walk_forward_result(
            supportive=False,
            rejection_reasons=("window[0]:oos_sharpe_below_ratio", "insufficient_valid_oos_windows"),
        ),
        _pbo_result(),
        _stress_result(),
    )

    assert result.stage2_status.rejection_reasons == (
        "stage2:window[0]:oos_sharpe_below_ratio",
        "stage2:insufficient_valid_oos_windows",
    )


def test_pbo_reasons_are_prefixed_correctly():
    result = validate_pipeline(
        _walk_forward_result(),
        _pbo_result(
            approved=False,
            pbo_action="rejected",
            rejection_reasons=("pbo_rejected", "dsr_negative"),
        ),
        _stress_result(),
    )

    assert result.pbo_status.rejection_reasons == ("pbo:pbo_rejected", "pbo:dsr_negative")


def test_stage3_reasons_are_prefixed_correctly():
    result = validate_pipeline(
        _walk_forward_result(),
        _pbo_result(),
        _stress_result(
            all_passed=False, rejection_reasons=("high_vol:negative_expectancy", "regime_gate[0]:undocumented")
        ),
    )

    assert result.stage3_status.rejection_reasons == (
        "stage3:high_vol:negative_expectancy",
        "stage3:regime_gate[0]:undocumented",
    )


def test_missing_stages_field_is_populated_deterministically():
    assert validate_pipeline(None, _pbo_result(), _stress_result()).missing_stages == (
        "stage2_walk_forward",
        "pbo",
        "stage3_stress",
    )
    assert validate_pipeline(_walk_forward_result(), None, _stress_result()).missing_stages == ("pbo", "stage3_stress")
    assert validate_pipeline(_walk_forward_result(), _pbo_result(), None).missing_stages == ("stage3_stress",)


def test_repeated_output_is_deterministic():
    payload = (
        _walk_forward_result(),
        _pbo_result(approved=True, pbo_action="approved_capped", allocation_cap=0.5),
        _stress_result(),
    )
    assert validate_pipeline(*payload) == validate_pipeline(*payload)


def test_validation_exports_import_correctly():
    assert validation_module.ValidationPipelineStageStatus is ValidationPipelineStageStatus
    assert validation_module.ValidationPipelineResult is ValidationPipelineResult
    assert validation_module.validate_pipeline is validate_pipeline
