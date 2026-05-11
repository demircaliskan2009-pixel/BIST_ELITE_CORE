from __future__ import annotations

import pytest

import crypto_core.validation as validation_module
from crypto_core.validation import WalkForwardWindow, build_stage4_backtest_baseline_from_windows


def _window(
    **overrides: float | int | str,
) -> WalkForwardWindow:
    values = {
        "window_id": "wf-001",
        "in_sample_sharpe": 2.0,
        "out_of_sample_sharpe": 1.0,
        "oos_expectancy": 0.1,
        "in_sample_hit_rate": 0.60,
        "out_of_sample_hit_rate": 0.55,
        "trade_count": 20,
        "evidence_count": 5,
        "in_sample_max_drawdown": 1.0,
        "oos_max_drawdown": 1.5,
        "oos_profit_factor": 1.2,
    }
    values.update(overrides)
    return WalkForwardWindow(**values)


def test_baseline_from_windows_happy_path_mean_oos_metrics():
    baseline = build_stage4_backtest_baseline_from_windows(
        (
            _window(window_id="wf-001", out_of_sample_sharpe=1.0, out_of_sample_hit_rate=0.40),
            _window(window_id="wf-002", out_of_sample_sharpe=2.0, out_of_sample_hit_rate=0.50),
            _window(window_id="wf-003", out_of_sample_sharpe=3.0, out_of_sample_hit_rate=0.60),
        ),
        baseline_id="baseline-001",
        edge_id="edge-alpha",
        as_of_ns=123,
    )

    assert baseline.baseline_id == "baseline-001"
    assert baseline.edge_id == "edge-alpha"
    assert baseline.as_of_ns == 123
    assert baseline.backtest_sharpe == pytest.approx(2.0)
    assert baseline.backtest_hit_rate == pytest.approx(0.5)
    assert baseline.source_window_ids == ("wf-001", "wf-002", "wf-003")


def test_baseline_from_windows_empty_raises():
    with pytest.raises(ValueError, match="stage4: no valid OOS windows for baseline"):
        build_stage4_backtest_baseline_from_windows(
            (),
            baseline_id="baseline-001",
            edge_id="edge-alpha",
            as_of_ns=123,
        )


def test_baseline_from_windows_all_invalid_raises():
    with pytest.raises(ValueError, match="stage4: no valid OOS windows for baseline"):
        build_stage4_backtest_baseline_from_windows(
            (
                _window(window_id="wf-001", out_of_sample_sharpe=float("nan")),
                _window(window_id="wf-002", out_of_sample_hit_rate=1.1),
            ),
            baseline_id="baseline-001",
            edge_id="edge-alpha",
            as_of_ns=123,
        )


def test_baseline_from_windows_partial_valid_uses_only_valid_windows():
    baseline = build_stage4_backtest_baseline_from_windows(
        [
            _window(window_id="wf-001", out_of_sample_sharpe=1.5, out_of_sample_hit_rate=0.45),
            _window(window_id="wf-002", out_of_sample_sharpe=float("nan")),
            _window(window_id="wf-003", out_of_sample_sharpe=2.5, out_of_sample_hit_rate=0.65),
        ],
        baseline_id="baseline-001",
        edge_id="edge-alpha",
        as_of_ns=123,
    )

    assert baseline.backtest_sharpe == pytest.approx(2.0)
    assert baseline.backtest_hit_rate == pytest.approx(0.55)
    assert baseline.source_window_ids == ("wf-001", "wf-003")


def test_baseline_from_windows_preserves_valid_window_id_order():
    baseline = build_stage4_backtest_baseline_from_windows(
        [
            _window(window_id="wf-003", out_of_sample_sharpe=1.0, out_of_sample_hit_rate=0.30),
            _window(window_id="wf-001", out_of_sample_sharpe=float("nan")),
            _window(window_id="wf-002", out_of_sample_sharpe=2.0, out_of_sample_hit_rate=0.40),
        ],
        baseline_id="baseline-001",
        edge_id="edge-alpha",
        as_of_ns=123,
    )

    assert baseline.source_window_ids == ("wf-003", "wf-002")


def test_baseline_builder_export_imports():
    assert validation_module.build_stage4_backtest_baseline_from_windows is build_stage4_backtest_baseline_from_windows
    assert "build_stage4_backtest_baseline_from_windows" in validation_module.__all__
