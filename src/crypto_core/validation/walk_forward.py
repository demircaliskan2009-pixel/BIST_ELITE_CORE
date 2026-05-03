"""Deterministic walk-forward validation foundation."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class WalkForwardWindow:
    window_id: str
    in_sample_sharpe: float
    out_of_sample_sharpe: float
    oos_expectancy: float
    in_sample_hit_rate: float
    out_of_sample_hit_rate: float
    trade_count: int
    evidence_count: int


@dataclass(frozen=True)
class WalkForwardWindowResult:
    window_id: str
    valid: bool
    supportive: bool
    expectancy_supportive: bool
    rejection_reasons: tuple[str, ...]


@dataclass(frozen=True)
class WalkForwardValidationResult:
    supportive: bool
    total_window_count: int
    valid_oos_window_count: int
    supportive_window_count: int
    positive_expectancy_window_count: int
    required_positive_expectancy_window_count: int
    rejection_reasons: tuple[str, ...]
    window_results: tuple[WalkForwardWindowResult, ...]


def _reason(index: int, code: str) -> str:
    return f"window[{index}]:{code}"


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _is_positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _result(
    window_id: str,
    valid: bool,
    supportive: bool,
    expectancy_supportive: bool,
    *reasons: str,
) -> WalkForwardWindowResult:
    return WalkForwardWindowResult(window_id, valid, supportive, expectancy_supportive, tuple(reasons))


def _evaluate_window(
    window: WalkForwardWindow | None,
    index: int,
    min_oos_sharpe_ratio: float,
    min_hit_rate_delta_pp: float,
) -> WalkForwardWindowResult:
    if not isinstance(window, WalkForwardWindow):
        return _result(f"window[{index}]", False, False, False, _reason(index, "malformed"))
    reasons: list[str] = []
    if not _is_number(window.in_sample_sharpe):
        reasons.append(_reason(index, "malformed_in_sample_sharpe"))
    if not _is_number(window.out_of_sample_sharpe):
        reasons.append(_reason(index, "malformed_out_of_sample_sharpe"))
    if not _is_number(window.oos_expectancy):
        reasons.append(_reason(index, "malformed_oos_expectancy"))
    if not _is_number(window.in_sample_hit_rate):
        reasons.append(_reason(index, "malformed_in_sample_hit_rate"))
    if not _is_number(window.out_of_sample_hit_rate):
        reasons.append(_reason(index, "malformed_out_of_sample_hit_rate"))
    if reasons:
        return _result(window.window_id, False, False, False, *reasons)
    if not _is_positive_int(window.trade_count):
        reasons.append(_reason(index, "non_positive_trade_count"))
    if not _is_positive_int(window.evidence_count):
        reasons.append(_reason(index, "non_positive_evidence_count"))
    if reasons:
        return _result(window.window_id, False, False, False, *reasons)
    if float(window.out_of_sample_sharpe) < float(window.in_sample_sharpe) * min_oos_sharpe_ratio:
        reasons.append(_reason(index, "oos_sharpe_below_ratio"))
    if float(window.out_of_sample_hit_rate) < float(window.in_sample_hit_rate) + min_hit_rate_delta_pp:
        reasons.append(_reason(index, "oos_hit_rate_below_delta"))
    expectancy_supportive = float(window.oos_expectancy) > 0.0
    return _result(window.window_id, True, not reasons, expectancy_supportive, *reasons)


def validate_walk_forward(
    windows: list[WalkForwardWindow | None] | tuple[WalkForwardWindow | None, ...] | None,
    *,
    min_oos_windows: int = 3,
    min_oos_sharpe_ratio: float = 0.5,
    min_hit_rate_delta_pp: float = -10.0,
) -> WalkForwardValidationResult:
    if windows is None:
        return WalkForwardValidationResult(False, 0, 0, 0, 0, 0, ("windows_missing",), ())
    try:
        ordered_windows = tuple(windows)
    except TypeError:
        return WalkForwardValidationResult(False, 0, 0, 0, 0, 0, ("windows_unreadable",), ())
    if not ordered_windows:
        return WalkForwardValidationResult(False, 0, 0, 0, 0, 0, ("windows_empty",), ())
    window_results = tuple(
        _evaluate_window(window, index, min_oos_sharpe_ratio, min_hit_rate_delta_pp)
        for index, window in enumerate(ordered_windows)
    )
    valid_oos_window_count = sum(result.valid for result in window_results)
    supportive_window_count = sum(result.supportive for result in window_results)
    positive_expectancy_window_count = sum(result.valid and result.expectancy_supportive for result in window_results)
    required_positive_expectancy_window_count = math.ceil(valid_oos_window_count * 2 / 3)
    rejection_reasons = tuple(reason for result in window_results for reason in result.rejection_reasons)
    if valid_oos_window_count < min_oos_windows:
        rejection_reasons += ("insufficient_valid_oos_windows",)
    if positive_expectancy_window_count < required_positive_expectancy_window_count:
        rejection_reasons += ("insufficient_positive_expectancy_windows",)
    return WalkForwardValidationResult(
        supportive=(
            not rejection_reasons
            and valid_oos_window_count >= min_oos_windows
            and positive_expectancy_window_count >= required_positive_expectancy_window_count
        ),
        total_window_count=len(ordered_windows),
        valid_oos_window_count=valid_oos_window_count,
        supportive_window_count=supportive_window_count,
        positive_expectancy_window_count=positive_expectancy_window_count,
        required_positive_expectancy_window_count=required_positive_expectancy_window_count,
        rejection_reasons=rejection_reasons,
        window_results=window_results,
    )
