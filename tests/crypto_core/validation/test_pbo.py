from __future__ import annotations

import pytest

from crypto_core import validation as validation_module
from crypto_core.validation import (
    CSCVMatrix,
    DSRInputs,
    MCPermutationInputs,
    PBOSplit,
    PBOValidationResult,
    RegimePBOResult,
    SensitivityInputs,
    validate_pbo,
)
from crypto_core.validation.pbo import MC_REQUIRED_SHUFFLE_COUNT, PBO_REQUIRED_SPLIT_COUNT, PBO_SUB_PERIOD_COUNT

_CONFIG_IDS = ("cfg-a", "cfg-b", "cfg-c", "cfg-d")


def _splits(
    bad_count: int,
    *,
    split_count: int = PBO_REQUIRED_SPLIT_COUNT,
    config_ids: tuple[str, ...] = _CONFIG_IDS,
) -> tuple[PBOSplit, ...]:
    return tuple(
        PBOSplit(
            split_index=index,
            selected_config_id=config_ids[0],
            oos_rank_of_selected=3 if index < bad_count else 1,
            total_configs=len(config_ids),
        )
        for index in range(split_count)
    )


def _matrix(
    bad_count: int = 1000,
    *,
    sub_period_count: int = PBO_SUB_PERIOD_COUNT,
    split_count: int = PBO_REQUIRED_SPLIT_COUNT,
    config_ids: tuple[str, ...] = _CONFIG_IDS,
    splits: tuple[PBOSplit, ...] | None = None,
) -> CSCVMatrix:
    return CSCVMatrix(
        config_ids=config_ids,
        sub_period_count=sub_period_count,
        splits=splits if splits is not None else _splits(bad_count, split_count=split_count, config_ids=config_ids),
    )


def _dsr_pass() -> DSRInputs:
    return DSRInputs(observed_sharpe=3.0, n_strategies_tested=1)


def _mc_pass() -> MCPermutationInputs:
    return MCPermutationInputs(
        observed_sharpe=3.0,
        shuffled_sharpes=(0.0,) * MC_REQUIRED_SHUFFLE_COUNT,
    )


def _mc_reject() -> MCPermutationInputs:
    return MCPermutationInputs(
        observed_sharpe=1.0,
        shuffled_sharpes=(1.1,) * 600 + (0.0,) * (MC_REQUIRED_SHUFFLE_COUNT - 600),
    )


def _sensitivity_pass(parameter_id: str = "lookback") -> SensitivityInputs:
    return SensitivityInputs(
        parameter_id=parameter_id,
        observed_sharpe=2.0,
        sharpes_at_steps=(1.6, 1.7, 1.4, 1.3, 2.0, 1.4, 1.3, 1.7, 1.6),
    )


def test_approved_when_pbo_below_threshold_and_dsr_mc_pass():
    result = validate_pbo(_matrix(1000), _dsr_pass(), _mc_pass())
    assert result.approved is True
    assert result.pbo_action == "approved"
    assert result.allocation_cap is None
    assert result.pbo_value == pytest.approx(1000 / PBO_REQUIRED_SPLIT_COUNT)
    assert result.dsr_passed is True
    assert result.mc_passed is True
    assert result.rejection_reasons == ()
    assert result.cscv_matrix_stored is True


def test_approved_capped_when_pbo_is_moderate():
    result = validate_pbo(_matrix(3000), _dsr_pass(), _mc_pass())
    assert result.approved is True
    assert result.pbo_action == "approved_capped"
    assert result.allocation_cap == 0.5
    assert result.rejection_reasons == ()


def test_requires_additional_oos_when_pbo_is_high():
    result = validate_pbo(_matrix(6000), _dsr_pass(), _mc_pass())
    assert result.approved is False
    assert result.pbo_action == "requires_additional_oos"
    assert result.allocation_cap is None
    assert result.rejection_reasons == ("pbo_requires_additional_oos",)


def test_rejected_when_pbo_is_likely_overfit():
    result = validate_pbo(_matrix(9000), _dsr_pass(), _mc_pass())
    assert result.approved is False
    assert result.pbo_action == "rejected"
    assert result.rejection_reasons == ("pbo_rejected",)


def test_dsr_negative_rejects():
    result = validate_pbo(_matrix(), DSRInputs(observed_sharpe=2.0, n_strategies_tested=4), _mc_pass())
    assert result.approved is False
    assert result.dsr_passed is False
    assert result.dsr_value is not None
    assert result.dsr_value < 0.0
    assert result.rejection_reasons == ("dsr_negative",)


def test_invalid_dsr_probability_fails_closed():
    result = validate_pbo(_matrix(), DSRInputs(observed_sharpe=0.0, n_strategies_tested=1), _mc_pass())
    assert result.approved is False
    assert result.dsr_value is None
    assert result.dsr_passed is False
    assert result.rejection_reasons == ("dsr_probability_invalid",)


def test_mc_p_value_above_threshold_rejects():
    result = validate_pbo(_matrix(), _dsr_pass(), _mc_reject())
    assert result.approved is False
    assert result.mc_passed is False
    assert result.mc_p_value == pytest.approx(0.06)
    assert result.rejection_reasons == ("mc_rejected",)


def test_wrong_mc_shuffle_count_fails_closed():
    result = validate_pbo(
        _matrix(),
        _dsr_pass(),
        MCPermutationInputs(observed_sharpe=2.0, shuffled_sharpes=(0.0,) * 9999),
    )
    assert result.approved is False
    assert result.mc_p_value is None
    assert result.mc_passed is False
    assert result.rejection_reasons == ("mc_wrong_shuffle_count",)


def test_sensitivity_fragile_rejects():
    result = validate_pbo(
        _matrix(),
        _dsr_pass(),
        _mc_pass(),
        sensitivity_inputs=(
            SensitivityInputs(
                parameter_id="lookback",
                observed_sharpe=2.0,
                sharpes_at_steps=(1.6, 1.7, 1.4, 0.9, 2.0, 1.3, 1.2, 1.7, 1.6),
            ),
        ),
    )
    assert result.approved is False
    assert result.sensitivity_fragile is True
    assert result.rejection_reasons == ("sensitivity_fragile:lookback",)


def test_malformed_sensitivity_input_fails_closed():
    result = validate_pbo(
        _matrix(),
        _dsr_pass(),
        _mc_pass(),
        sensitivity_inputs=(SensitivityInputs(parameter_id="", observed_sharpe=2.0, sharpes_at_steps=(1.0,) * 9),),
    )
    assert result.approved is False
    assert result.sensitivity_fragile is False
    assert result.rejection_reasons == ("sensitivity[0]:empty_parameter_id",)


def test_regime_pbo_above_cap_threshold_caps_regime_and_preserves_global_approval():
    result = validate_pbo(
        _matrix(),
        _dsr_pass(),
        _mc_pass(),
        regime_cscv={"BEAR": _matrix(6000)},
    )
    assert result.approved is True
    assert result.regime_pbo == (
        validation_module.RegimePBOResult(
            regime="BEAR",
            pbo_value=6000 / PBO_REQUIRED_SPLIT_COUNT,
            allocation_cap=0.25,
            rejection_reason="regime_pbo_high:BEAR",
        ),
    )
    assert result.rejection_reasons == ("regime_pbo_high:BEAR",)


def test_missing_cscv_matrix_fails_closed():
    result = validate_pbo(None, _dsr_pass(), _mc_pass())
    assert result.approved is False
    assert result.pbo_value is None
    assert result.pbo_action is None
    assert result.cscv_matrix_stored is False
    assert result.rejection_reasons == ("cscv_matrix_missing",)


def test_wrong_split_count_fails_closed():
    result = validate_pbo(_matrix(split_count=PBO_REQUIRED_SPLIT_COUNT - 1), _dsr_pass(), _mc_pass())
    assert result.approved is False
    assert result.cscv_matrix_stored is False
    assert result.rejection_reasons == ("cscv_wrong_split_count",)


def test_wrong_sub_period_count_fails_closed():
    result = validate_pbo(_matrix(sub_period_count=15), _dsr_pass(), _mc_pass())
    assert result.approved is False
    assert result.cscv_matrix_stored is False
    assert result.rejection_reasons == ("cscv_wrong_sub_period_count",)


def test_malformed_split_fails_closed():
    malformed_splits = (PBOSplit(-1, "cfg-a", 1, len(_CONFIG_IDS)),) + _splits(1000)[1:]
    result = validate_pbo(_matrix(splits=malformed_splits), _dsr_pass(), _mc_pass())
    assert result.approved is False
    assert result.cscv_matrix_stored is False
    assert result.rejection_reasons == ("split[0]:invalid_split_index",)


def test_duplicate_split_index_fails_closed():
    splits = _splits(1000)
    duplicate_split = PBOSplit(0, "cfg-a", 1, len(_CONFIG_IDS))
    result = validate_pbo(_matrix(splits=(splits[0], duplicate_split, *splits[2:])), _dsr_pass(), _mc_pass())
    assert result.approved is False
    assert result.cscv_matrix_stored is False
    assert result.rejection_reasons == ("split[1]:duplicate_split_index",)


def test_config_ids_must_be_unique():
    result = validate_pbo(_matrix(config_ids=("cfg-a", "cfg-a", "cfg-b", "cfg-c")), _dsr_pass(), _mc_pass())
    assert result.approved is False
    assert result.cscv_matrix_stored is False
    assert result.rejection_reasons == ("config[1]:duplicate_config_id",)


def test_missing_dsr_inputs_fails_closed():
    result = validate_pbo(_matrix(), None, _mc_pass())
    assert result.approved is False
    assert result.dsr_passed is False
    assert result.rejection_reasons == ("dsr_inputs_missing",)


def test_missing_mc_inputs_fails_closed():
    result = validate_pbo(_matrix(), _dsr_pass(), None)
    assert result.approved is False
    assert result.mc_passed is False
    assert result.rejection_reasons == ("mc_inputs_missing",)


def test_deterministic_repeated_output():
    payload = (
        _matrix(3000),
        _dsr_pass(),
        _mc_pass(),
        (_sensitivity_pass(),),
        {"BULL": _matrix(1000), "NEUTRAL": _matrix(6000)},
    )
    assert validate_pbo(*payload) == validate_pbo(*payload)


def test_rejection_reasons_stable_and_ordered():
    result = validate_pbo(
        _matrix(6000),
        DSRInputs(observed_sharpe=2.0, n_strategies_tested=4),
        _mc_reject(),
        sensitivity_inputs=(
            SensitivityInputs(
                parameter_id="lookback",
                observed_sharpe=2.0,
                sharpes_at_steps=(1.6, 1.7, 1.4, 0.9, 2.0, 1.3, 1.2, 1.7, 1.6),
            ),
        ),
        regime_cscv={"NEUTRAL": _matrix(6000), "BULL": _matrix(6000)},
    )
    assert result.approved is False
    assert result.rejection_reasons == (
        "pbo_requires_additional_oos",
        "dsr_negative",
        "mc_rejected",
        "sensitivity_fragile:lookback",
        "regime_pbo_high:BULL",
        "regime_pbo_high:NEUTRAL",
    )


def test_validation_exports_import_correctly():
    assert validation_module.PBOSplit is PBOSplit
    assert validation_module.CSCVMatrix is CSCVMatrix
    assert validation_module.DSRInputs is DSRInputs
    assert validation_module.MCPermutationInputs is MCPermutationInputs
    assert validation_module.SensitivityInputs is SensitivityInputs
    assert validation_module.RegimePBOResult is RegimePBOResult
    assert validation_module.PBOValidationResult is PBOValidationResult
    assert validation_module.validate_pbo is validate_pbo
