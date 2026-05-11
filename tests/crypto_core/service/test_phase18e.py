from __future__ import annotations

import importlib

from crypto_core.service.paper_shadow_session_controller import (
    PaperShadowSessionSnapshot,
    PaperShadowSessionStatus,
    build_stage4_paper_summary_from_session_snapshot,
)
from crypto_core.validation import WalkForwardWindow, build_stage4_backtest_baseline_from_windows, compare_stage4

_DAY_NS = 86400 * 1_000_000_000


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


def _snapshot(
    **overrides: int | str | None,
) -> PaperShadowSessionSnapshot:
    values = {
        "session_id": "paper-session-001",
        "status": PaperShadowSessionStatus.STOPPED,
        "as_of_ns": 31 * _DAY_NS + 5,
        "prepared_at_ns": 1,
        "started_at_ns": 2,
        "stopped_at_ns": 31 * _DAY_NS + 2,
        "fill_attempts": 10,
        "simulated_fills": 8,
        "rejected_fills": 2,
    }
    values.update(overrides)
    return PaperShadowSessionSnapshot(**values)


def _baseline():
    return build_stage4_backtest_baseline_from_windows(
        (
            _window(window_id="wf-001", out_of_sample_sharpe=1.8, out_of_sample_hit_rate=0.52),
            _window(window_id="wf-002", out_of_sample_sharpe=2.2, out_of_sample_hit_rate=0.58),
        ),
        baseline_id="baseline-001",
        edge_id="edge-alpha",
        as_of_ns=31 * _DAY_NS,
    )


def test_paper_summary_from_snapshot_happy_path_duration_fields():
    summary = build_stage4_paper_summary_from_session_snapshot(_snapshot(), edge_id="edge-alpha")

    assert summary.paper_id == "paper-session-001"
    assert summary.edge_id == "edge-alpha"
    assert summary.started_at_ns == 2
    assert summary.stopped_at_ns == 31 * _DAY_NS + 2
    assert summary.session_duration_days == 31.0
    assert summary.paper_trade_count == 8


def test_paper_summary_from_snapshot_fill_rate():
    summary = build_stage4_paper_summary_from_session_snapshot(
        _snapshot(fill_attempts=10, simulated_fills=8),
        edge_id="edge-alpha",
    )

    assert summary.paper_fill_rate == 0.8


def test_paper_summary_from_snapshot_zero_fill_attempts_sets_fill_rate_none():
    summary = build_stage4_paper_summary_from_session_snapshot(
        _snapshot(fill_attempts=0, simulated_fills=0, rejected_fills=0),
        edge_id="edge-alpha",
    )

    assert summary.paper_fill_rate is None


def test_paper_summary_from_snapshot_paper_sharpe_is_none_fail_closed():
    summary = build_stage4_paper_summary_from_session_snapshot(_snapshot(), edge_id="edge-alpha")

    assert summary.paper_sharpe is None
    assert summary.paper_hit_rate is None
    assert summary.paper_slippage_bps is None


def test_paper_summary_from_snapshot_missing_started_time_yields_invalid_summary_for_compare_stage4():
    summary = build_stage4_paper_summary_from_session_snapshot(
        _snapshot(
            status=PaperShadowSessionStatus.READY,
            started_at_ns=None,
            stopped_at_ns=None,
            fill_attempts=0,
            simulated_fills=0,
            rejected_fills=0,
        ),
        edge_id="edge-alpha",
    )
    result = compare_stage4(_baseline(), summary)

    assert summary.started_at_ns == 0
    assert summary.session_duration_days is None
    assert result.status == "INSUFFICIENT_EVIDENCE"
    assert "stage4:paper_time_invalid" in result.rejection_reasons


def test_paper_summary_builder_imports_without_breaking_paper_shadow_controller():
    module = importlib.import_module("crypto_core.service.paper_shadow_session_controller")

    assert module.build_stage4_paper_summary_from_session_snapshot is build_stage4_paper_summary_from_session_snapshot


def test_service_builder_does_not_require_backtest_metrics_or_comparator_pass():
    summary = build_stage4_paper_summary_from_session_snapshot(_snapshot(), edge_id="edge-alpha")

    assert summary.paper_id == "paper-session-001"
    assert summary.paper_sharpe is None
    assert summary.paper_hit_rate is None


def test_stage4_builders_integration_returns_insufficient_evidence_when_paper_sharpe_missing():
    baseline = _baseline()
    paper_summary = build_stage4_paper_summary_from_session_snapshot(_snapshot(), edge_id="edge-alpha")
    result = compare_stage4(baseline, paper_summary)

    assert result.status == "INSUFFICIENT_EVIDENCE"
    assert "stage4:paper_sharpe_not_computable" in result.rejection_reasons
