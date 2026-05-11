"""Deterministic PBO / CSCV overfitting-control validation foundation."""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import NormalDist
from typing import Final

PBO_SUB_PERIOD_COUNT: Final = 16
PBO_REQUIRED_SPLIT_COUNT: Final = 12870
MC_REQUIRED_SHUFFLE_COUNT: Final = 10000
PBO_APPROVED_THRESHOLD: Final = 0.20
PBO_CAPPED_THRESHOLD: Final = 0.40
PBO_REQUIRES_OOS_THRESHOLD: Final = 0.60
MC_P_VALUE_REJECT_THRESHOLD: Final = 0.05
SENSITIVITY_DROP_REJECT_THRESHOLD: Final = 0.50
REGIME_PBO_CAP_THRESHOLD: Final = 0.40

_ALLOWED_REGIMES: Final = ("BULL", "BEAR", "NEUTRAL")
_SENSITIVITY_LOCAL_STEP_INDICES: Final = (2, 3, 4, 5, 6)


@dataclass(frozen=True)
class PBOSplit:
    split_index: int
    selected_config_id: str
    oos_rank_of_selected: int
    total_configs: int


@dataclass(frozen=True)
class CSCVMatrix:
    config_ids: tuple[str, ...]
    sub_period_count: int
    splits: tuple[PBOSplit, ...]


@dataclass(frozen=True)
class DSRInputs:
    observed_sharpe: float
    n_strategies_tested: int


@dataclass(frozen=True)
class MCPermutationInputs:
    observed_sharpe: float
    shuffled_sharpes: tuple[float, ...]


@dataclass(frozen=True)
class SensitivityInputs:
    parameter_id: str
    sharpes_at_steps: tuple[float, ...]
    observed_sharpe: float


@dataclass(frozen=True)
class RegimePBOResult:
    regime: str
    pbo_value: float
    allocation_cap: float | None
    rejection_reason: str | None


@dataclass(frozen=True)
class PBOValidationResult:
    approved: bool
    pbo_value: float | None
    pbo_action: str | None
    allocation_cap: float | None
    dsr_value: float | None
    dsr_passed: bool
    mc_p_value: float | None
    mc_passed: bool
    regime_pbo: tuple[RegimePBOResult, ...]
    sensitivity_fragile: bool
    cscv_matrix_stored: bool
    rejection_reasons: tuple[str, ...]


def _is_finite_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_non_empty_str(value: object) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _validate_split(
    split: PBOSplit | None,
    index: int,
    config_ids: frozenset[str],
    total_config_count: int,
    seen_split_indices: set[int],
) -> tuple[str, ...]:
    if not isinstance(split, PBOSplit):
        return (f"split[{index}]:malformed",)
    reasons: list[str] = []
    split_index_is_valid = _is_int(split.split_index) and split.split_index >= 0
    total_configs_is_valid = _is_int(split.total_configs) and split.total_configs >= 2
    if not split_index_is_valid:
        reasons.append(f"split[{index}]:invalid_split_index")
    elif split.split_index in seen_split_indices:
        reasons.append(f"split[{index}]:duplicate_split_index")
    else:
        seen_split_indices.add(split.split_index)
    if not _is_non_empty_str(split.selected_config_id):
        reasons.append(f"split[{index}]:empty_selected_config_id")
    elif split.selected_config_id not in config_ids:
        reasons.append(f"split[{index}]:unknown_selected_config_id")
    if not total_configs_is_valid:
        reasons.append(f"split[{index}]:invalid_total_configs")
    elif split.total_configs != total_config_count:
        reasons.append(f"split[{index}]:total_configs_mismatch")
    if (
        not _is_int(split.oos_rank_of_selected)
        or not total_configs_is_valid
        or not 1 <= split.oos_rank_of_selected <= split.total_configs
    ):
        reasons.append(f"split[{index}]:invalid_oos_rank_of_selected")
    return tuple(reasons)


def _validate_cscv_matrix(
    matrix: CSCVMatrix | None, reason_prefix: str = "cscv"
) -> tuple[CSCVMatrix | None, tuple[str, ...]]:
    if matrix is None:
        return None, (f"{reason_prefix}_matrix_missing",)
    if not isinstance(matrix, CSCVMatrix):
        return None, (f"{reason_prefix}_matrix_malformed",)
    reasons: list[str] = []
    if matrix.sub_period_count != PBO_SUB_PERIOD_COUNT:
        reasons.append(f"{reason_prefix}_wrong_sub_period_count")
    if not isinstance(matrix.config_ids, tuple):
        reasons.append(f"{reason_prefix}_config_ids_malformed")
        config_ids: tuple[str, ...] = ()
    else:
        config_ids = matrix.config_ids
    if not isinstance(matrix.splits, tuple):
        reasons.append(f"{reason_prefix}_splits_malformed")
        splits: tuple[PBOSplit | None, ...] = ()
    else:
        splits = matrix.splits
    if len(splits) != PBO_REQUIRED_SPLIT_COUNT:
        reasons.append(f"{reason_prefix}_wrong_split_count")
    if len(config_ids) < 2:
        reasons.append(f"{reason_prefix}_insufficient_config_ids")
    seen_config_ids: set[str] = set()
    valid_config_ids: set[str] = set()
    for index, config_id in enumerate(config_ids):
        if not _is_non_empty_str(config_id):
            reasons.append(f"config[{index}]:empty_config_id")
            continue
        if config_id in seen_config_ids:
            reasons.append(f"config[{index}]:duplicate_config_id")
            continue
        seen_config_ids.add(config_id)
        valid_config_ids.add(config_id)
    seen_split_indices: set[int] = set()
    for index, split in enumerate(splits):
        reasons.extend(_validate_split(split, index, frozenset(valid_config_ids), len(config_ids), seen_split_indices))
    if reasons:
        return None, tuple(reasons)
    return matrix, ()


def _compute_pbo_value(matrix: CSCVMatrix) -> float:
    bad_split_count = sum(split.oos_rank_of_selected > split.total_configs / 2 for split in matrix.splits)
    return bad_split_count / len(matrix.splits)


def _pbo_decision(pbo_value: float) -> tuple[str, float | None, tuple[str, ...], bool]:
    if pbo_value < PBO_APPROVED_THRESHOLD:
        return "approved", None, (), True
    if pbo_value < PBO_CAPPED_THRESHOLD:
        return "approved_capped", 0.5, (), True
    if pbo_value <= PBO_REQUIRES_OOS_THRESHOLD:
        return "requires_additional_oos", None, ("pbo_requires_additional_oos",), False
    return "rejected", None, ("pbo_rejected",), False


def _evaluate_dsr(dsr_inputs: DSRInputs | None) -> tuple[float | None, bool, tuple[str, ...]]:
    if dsr_inputs is None:
        return None, False, ("dsr_inputs_missing",)
    if not isinstance(dsr_inputs, DSRInputs):
        return None, False, ("dsr_inputs_malformed",)
    reasons: list[str] = []
    if not _is_finite_number(dsr_inputs.observed_sharpe):
        reasons.append("dsr_observed_sharpe_malformed")
    if not _is_int(dsr_inputs.n_strategies_tested) or dsr_inputs.n_strategies_tested <= 0:
        reasons.append("dsr_n_strategies_tested_malformed")
    if reasons:
        return None, False, tuple(reasons)
    try:
        denominator = math.exp(float(dsr_inputs.observed_sharpe) ** 2 / 2.0)
    except OverflowError:
        denominator = math.inf
    probability = 1.0 - float(dsr_inputs.n_strategies_tested) / denominator
    if probability <= 0.0 or probability >= 1.0:
        return None, False, ("dsr_probability_invalid",)
    dsr_value = NormalDist().inv_cdf(probability)
    if dsr_value < 0.0:
        return dsr_value, False, ("dsr_negative",)
    return dsr_value, True, ()


def _evaluate_mc(mc_inputs: MCPermutationInputs | None) -> tuple[float | None, bool, tuple[str, ...]]:
    if mc_inputs is None:
        return None, False, ("mc_inputs_missing",)
    if not isinstance(mc_inputs, MCPermutationInputs):
        return None, False, ("mc_inputs_malformed",)
    reasons: list[str] = []
    if not _is_finite_number(mc_inputs.observed_sharpe):
        reasons.append("mc_observed_sharpe_malformed")
    if not isinstance(mc_inputs.shuffled_sharpes, tuple):
        reasons.append("mc_shuffled_sharpes_malformed")
        shuffled_sharpes: tuple[float, ...] = ()
    else:
        shuffled_sharpes = mc_inputs.shuffled_sharpes
    if len(shuffled_sharpes) != MC_REQUIRED_SHUFFLE_COUNT:
        reasons.append("mc_wrong_shuffle_count")
    invalid_sharpe_count = sum(not _is_finite_number(sharpe) for sharpe in shuffled_sharpes)
    if invalid_sharpe_count:
        reasons.append("mc_shuffled_sharpe_malformed")
    if reasons:
        return None, False, tuple(reasons)
    mc_p_value = (
        sum(float(sharpe) >= float(mc_inputs.observed_sharpe) for sharpe in shuffled_sharpes)
        / MC_REQUIRED_SHUFFLE_COUNT
    )
    if mc_p_value > MC_P_VALUE_REJECT_THRESHOLD:
        return mc_p_value, False, ("mc_rejected",)
    return mc_p_value, True, ()


def _evaluate_sensitivity(
    sensitivity_inputs: tuple[SensitivityInputs, ...] | None,
) -> tuple[bool, tuple[str, ...], bool]:
    if sensitivity_inputs is None:
        return False, (), False
    if not isinstance(sensitivity_inputs, tuple):
        return False, ("sensitivity_inputs_malformed",), True
    rejection_reasons: list[str] = []
    fail_closed = False
    sensitivity_fragile = False
    for index, sensitivity_input in enumerate(sensitivity_inputs):
        if not isinstance(sensitivity_input, SensitivityInputs):
            rejection_reasons.append(f"sensitivity[{index}]:malformed")
            fail_closed = True
            continue
        input_reasons: list[str] = []
        if not _is_non_empty_str(sensitivity_input.parameter_id):
            input_reasons.append(f"sensitivity[{index}]:empty_parameter_id")
        if not _is_finite_number(sensitivity_input.observed_sharpe):
            input_reasons.append(f"sensitivity[{index}]:malformed_observed_sharpe")
        if not isinstance(sensitivity_input.sharpes_at_steps, tuple):
            input_reasons.append(f"sensitivity[{index}]:sharpes_at_steps_malformed")
            sharpes_at_steps: tuple[float, ...] = ()
        else:
            sharpes_at_steps = sensitivity_input.sharpes_at_steps
        if len(sharpes_at_steps) != 9:
            input_reasons.append(f"sensitivity[{index}]:wrong_step_count")
        if any(not _is_finite_number(sharpe) for sharpe in sharpes_at_steps):
            input_reasons.append(f"sensitivity[{index}]:malformed_sharpe")
        if input_reasons:
            rejection_reasons.extend(input_reasons)
            fail_closed = True
            continue
        if float(sensitivity_input.observed_sharpe) <= 0.0:
            rejection_reasons.append("sensitivity_observed_sharpe_non_positive")
            fail_closed = True
            continue
        fragile_threshold = float(sensitivity_input.observed_sharpe) * SENSITIVITY_DROP_REJECT_THRESHOLD
        if any(
            float(sharpes_at_steps[step_index]) < fragile_threshold for step_index in _SENSITIVITY_LOCAL_STEP_INDICES
        ):
            sensitivity_fragile = True
            rejection_reasons.append(f"sensitivity_fragile:{sensitivity_input.parameter_id}")
    return sensitivity_fragile, tuple(rejection_reasons), fail_closed


def _evaluate_regime_pbo(
    regime_cscv: dict[str, CSCVMatrix] | None,
) -> tuple[tuple[RegimePBOResult, ...], tuple[str, ...], bool]:
    if regime_cscv is None:
        return (), (), False
    if not isinstance(regime_cscv, dict):
        return (), ("regime_cscv_malformed",), True
    regime_results: list[RegimePBOResult] = []
    rejection_reasons: list[str] = []
    fail_closed = False
    unknown_regimes = tuple(sorted(regime for regime in regime_cscv if regime not in _ALLOWED_REGIMES))
    for regime in _ALLOWED_REGIMES:
        if regime not in regime_cscv:
            continue
        matrix, matrix_reasons = _validate_cscv_matrix(regime_cscv[regime], f"regime[{regime}]")
        if matrix_reasons or matrix is None:
            reason = f"regime_matrix_malformed:{regime}"
            regime_results.append(
                RegimePBOResult(regime=regime, pbo_value=0.0, allocation_cap=None, rejection_reason=reason)
            )
            rejection_reasons.extend(matrix_reasons or (reason,))
            fail_closed = True
            continue
        pbo_value = _compute_pbo_value(matrix)
        if pbo_value > REGIME_PBO_CAP_THRESHOLD:
            reason = f"regime_pbo_high:{regime}"
            regime_results.append(
                RegimePBOResult(regime=regime, pbo_value=pbo_value, allocation_cap=0.25, rejection_reason=reason)
            )
            rejection_reasons.append(reason)
        else:
            regime_results.append(
                RegimePBOResult(regime=regime, pbo_value=pbo_value, allocation_cap=None, rejection_reason=None)
            )
    for regime in unknown_regimes:
        rejection_reasons.append(f"regime_unknown:{regime}")
        fail_closed = True
    return tuple(regime_results), tuple(rejection_reasons), fail_closed


def validate_pbo(
    cscv_matrix: CSCVMatrix | None,
    dsr_inputs: DSRInputs | None,
    mc_inputs: MCPermutationInputs | None,
    sensitivity_inputs: tuple[SensitivityInputs, ...] | None = None,
    regime_cscv: dict[str, CSCVMatrix] | None = None,
) -> PBOValidationResult:
    valid_matrix, cscv_reasons = _validate_cscv_matrix(cscv_matrix)
    pbo_value: float | None = None
    pbo_action: str | None = None
    allocation_cap: float | None = None
    pbo_reasons: tuple[str, ...] = ()
    pbo_allows_approval = False
    if valid_matrix is not None:
        pbo_value = _compute_pbo_value(valid_matrix)
        pbo_action, allocation_cap, pbo_reasons, pbo_allows_approval = _pbo_decision(pbo_value)
    dsr_value, dsr_passed, dsr_reasons = _evaluate_dsr(dsr_inputs)
    mc_p_value, mc_passed, mc_reasons = _evaluate_mc(mc_inputs)
    sensitivity_fragile, sensitivity_reasons, sensitivity_fail_closed = _evaluate_sensitivity(sensitivity_inputs)
    regime_pbo, regime_reasons, regime_fail_closed = _evaluate_regime_pbo(regime_cscv)
    rejection_reasons = (
        *cscv_reasons,
        *pbo_reasons,
        *dsr_reasons,
        *mc_reasons,
        *sensitivity_reasons,
        *regime_reasons,
    )
    has_fail_closed_input_error = bool(cscv_reasons) or sensitivity_fail_closed or regime_fail_closed
    approved = (
        valid_matrix is not None
        and pbo_allows_approval
        and dsr_passed
        and mc_passed
        and not sensitivity_fragile
        and not has_fail_closed_input_error
    )
    return PBOValidationResult(
        approved=approved,
        pbo_value=pbo_value,
        pbo_action=pbo_action,
        allocation_cap=allocation_cap,
        dsr_value=dsr_value,
        dsr_passed=dsr_passed,
        mc_p_value=mc_p_value,
        mc_passed=mc_passed,
        regime_pbo=regime_pbo,
        sensitivity_fragile=sensitivity_fragile,
        cscv_matrix_stored=valid_matrix is not None,
        rejection_reasons=rejection_reasons,
    )
