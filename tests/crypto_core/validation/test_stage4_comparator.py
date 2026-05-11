from __future__ import annotations

import json

import crypto_core.validation as validation_module
from crypto_core.validation import (
    Stage4BacktestBaseline,
    Stage4ComparisonResult,
    Stage4PaperSummary,
    build_stage4_backtest_baseline,
    compare_stage4,
    stage4_backtest_baseline_to_dict,
    stage4_comparison_result_to_dict,
    stage4_paper_summary_to_dict,
)

_DAY_NS = 86400 * 1_000_000_000


def _baseline(
    **overrides: float | int | str | tuple[str, ...] | None,
) -> Stage4BacktestBaseline:
    values = {
        "baseline_id": "baseline-001",
        "edge_id": "edge-alpha",
        "as_of_ns": 31 * _DAY_NS,
        "backtest_sharpe": 2.0,
        "backtest_hit_rate": 0.60,
        "backtest_slippage_bps": None,
        "backtest_fill_rate": None,
        "source_window_ids": ("wf-1", "wf-2", "wf-3"),
    }
    values.update(overrides)
    return build_stage4_backtest_baseline(**values)


def _paper(
    **overrides: float | int | str | None,
) -> Stage4PaperSummary:
    values = {
        "paper_id": "paper-001",
        "edge_id": "edge-alpha",
        "started_at_ns": 1,
        "stopped_at_ns": 31 * _DAY_NS + 1,
        "paper_sharpe": 1.1,
        "paper_hit_rate": 0.58,
        "paper_slippage_bps": None,
        "paper_fill_rate": None,
        "paper_trade_count": 42,
    }
    values.update(overrides)
    return Stage4PaperSummary(**values)


def test_compare_stage4_passes_when_duration_and_sharpe_retention_pass():
    result = compare_stage4(_baseline(), _paper())

    assert result == Stage4ComparisonResult(
        evaluated=True,
        passed=True,
        status="PASS",
        baseline_id="baseline-001",
        paper_id="paper-001",
        edge_id="edge-alpha",
        session_duration_days=31.0,
        required_duration_days=30.0,
        backtest_sharpe=2.0,
        paper_sharpe=1.1,
        required_min_paper_sharpe=1.0,
        sharpe_retention_ratio=0.55,
        paper_hit_rate=0.58,
        backtest_hit_rate=0.60,
        paper_slippage_bps=None,
        backtest_slippage_bps=None,
        paper_fill_rate=None,
        backtest_fill_rate=None,
        rejection_reasons=(),
    )


def test_compare_stage4_rejects_duration_below_30_days():
    result = compare_stage4(_baseline(), _paper(stopped_at_ns=29 * _DAY_NS + 1))

    assert result.evaluated is True
    assert result.passed is False
    assert result.status == "REJECT"
    assert result.session_duration_days == 29.0
    assert result.rejection_reasons == ("stage4:duration_below_minimum",)


def test_compare_stage4_rejects_paper_sharpe_below_50pct_backtest():
    result = compare_stage4(_baseline(backtest_sharpe=2.0), _paper(paper_sharpe=0.99))

    assert result.evaluated is True
    assert result.status == "REJECT"
    assert result.required_min_paper_sharpe == 1.0
    assert result.rejection_reasons == ("stage4:paper_sharpe_below_backtest_threshold",)


def test_compare_stage4_equal_sharpe_threshold_passes():
    result = compare_stage4(_baseline(backtest_sharpe=2.0), _paper(paper_sharpe=1.0))

    assert result.status == "PASS"
    assert result.passed is True
    assert result.required_min_paper_sharpe == 1.0


def test_compare_stage4_missing_baseline_is_insufficient():
    result = compare_stage4(None, _paper())

    assert result.evaluated is False
    assert result.passed is False
    assert result.status == "INSUFFICIENT_EVIDENCE"
    assert result.rejection_reasons == ("stage4:backtest_baseline_missing",)


def test_compare_stage4_missing_paper_summary_is_insufficient():
    result = compare_stage4(_baseline(), None)

    assert result.evaluated is False
    assert result.passed is False
    assert result.status == "INSUFFICIENT_EVIDENCE"
    assert result.rejection_reasons == ("stage4:paper_summary_missing",)


def test_compare_stage4_nonpositive_backtest_sharpe_is_insufficient():
    result = compare_stage4(_baseline(backtest_sharpe=0.0), _paper())

    assert result.evaluated is False
    assert result.status == "INSUFFICIENT_EVIDENCE"
    assert result.backtest_sharpe == 0.0
    assert result.rejection_reasons == ("stage4:backtest_sharpe_non_positive",)


def test_compare_stage4_missing_or_nan_paper_sharpe_is_insufficient():
    result_missing = compare_stage4(_baseline(), _paper(paper_sharpe=None))
    result_nan = compare_stage4(_baseline(), _paper(paper_sharpe=float("nan")))

    assert result_missing.status == "INSUFFICIENT_EVIDENCE"
    assert result_missing.rejection_reasons == ("stage4:paper_sharpe_not_computable",)
    assert result_nan.status == "INSUFFICIENT_EVIDENCE"
    assert result_nan.rejection_reasons == ("stage4:paper_sharpe_not_computable",)
    assert result_nan.paper_sharpe is None


def test_compare_stage4_edge_id_mismatch_rejects():
    result = compare_stage4(_baseline(edge_id="edge-alpha"), _paper(edge_id="edge-beta"))

    assert result.evaluated is True
    assert result.status == "REJECT"
    assert result.rejection_reasons == ("stage4:edge_id_mismatch",)


def test_compare_stage4_invalid_hit_rates_are_insufficient():
    baseline_result = compare_stage4(_baseline(backtest_hit_rate=1.1), _paper())
    paper_result = compare_stage4(_baseline(), _paper(paper_hit_rate=-0.1))

    assert baseline_result.status == "INSUFFICIENT_EVIDENCE"
    assert baseline_result.rejection_reasons == ("stage4:backtest_hit_rate_invalid",)
    assert paper_result.status == "INSUFFICIENT_EVIDENCE"
    assert paper_result.rejection_reasons == ("stage4:paper_hit_rate_invalid",)


def test_compare_stage4_optional_slippage_and_fill_rates_are_visible():
    result = compare_stage4(
        _baseline(backtest_slippage_bps=12.5, backtest_fill_rate=0.93),
        _paper(paper_slippage_bps=14.0, paper_fill_rate=0.91),
    )

    assert result.status == "PASS"
    assert result.backtest_slippage_bps == 12.5
    assert result.paper_slippage_bps == 14.0
    assert result.backtest_fill_rate == 0.93
    assert result.paper_fill_rate == 0.91


def test_compare_stage4_rejection_reasons_are_stable_and_ordered():
    result = compare_stage4(
        _baseline(),
        _paper(
            paper_id="",
            edge_id="",
            started_at_ns=0,
            stopped_at_ns=0,
            paper_sharpe=None,
            paper_hit_rate=1.2,
            paper_slippage_bps=-1.0,
            paper_fill_rate=1.1,
            paper_trade_count=-1,
        ),
    )

    assert result.status == "INSUFFICIENT_EVIDENCE"
    assert result.rejection_reasons == (
        "stage4:paper_id_missing",
        "stage4:paper_edge_id_missing",
        "stage4:paper_time_invalid",
        "stage4:paper_sharpe_not_computable",
        "stage4:paper_hit_rate_invalid",
        "stage4:paper_slippage_invalid",
        "stage4:paper_fill_rate_invalid",
        "stage4:paper_trade_count_invalid",
    )


def test_compare_stage4_repeated_output_is_deterministic():
    baseline = _baseline(backtest_slippage_bps=10.0, backtest_fill_rate=0.95)
    paper = _paper(paper_slippage_bps=11.0, paper_fill_rate=0.92)

    assert compare_stage4(baseline, paper) == compare_stage4(baseline, paper)


def test_stage4_result_to_dict_is_json_safe():
    baseline = _baseline(backtest_slippage_bps=10.0, backtest_fill_rate=0.95)
    paper = _paper(paper_slippage_bps=11.0, paper_fill_rate=0.92)
    result = compare_stage4(baseline, paper)

    assert json.loads(json.dumps(stage4_backtest_baseline_to_dict(baseline)))["source_window_ids"] == [
        "wf-1",
        "wf-2",
        "wf-3",
    ]
    assert json.loads(json.dumps(stage4_paper_summary_to_dict(paper)))["session_duration_days"] == 31.0
    payload = json.loads(json.dumps(stage4_comparison_result_to_dict(result)))
    assert payload["status"] == "PASS"
    assert payload["rejection_reasons"] == []


def test_exports_import_correctly():
    assert validation_module.Stage4BacktestBaseline is Stage4BacktestBaseline
    assert validation_module.Stage4PaperSummary is Stage4PaperSummary
    assert validation_module.Stage4ComparisonResult is Stage4ComparisonResult
    assert validation_module.compare_stage4 is compare_stage4
    assert validation_module.build_stage4_backtest_baseline is build_stage4_backtest_baseline
    assert validation_module.stage4_backtest_baseline_to_dict is stage4_backtest_baseline_to_dict
    assert validation_module.stage4_paper_summary_to_dict is stage4_paper_summary_to_dict
    assert validation_module.stage4_comparison_result_to_dict is stage4_comparison_result_to_dict
    assert "Stage4BacktestBaseline" in validation_module.__all__
    assert "Stage4PaperSummary" in validation_module.__all__
    assert "Stage4ComparisonResult" in validation_module.__all__
