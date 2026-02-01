"""FAZ95: Eval gates contract — metrics -> pass/fail; fail -> exit 2 + artifacts."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from bist_core.eval.gates import evaluate, run_gates, GATE_MIN_TRADES, GATE_MAX_DD


def test_faz95_evaluate_pass() -> None:
    """Metrics pass all gates -> passed=True, failed_gates=[]."""
    metrics = {"total_fills": 10, "max_drawdown": 0.05}
    gates = {GATE_MIN_TRADES: 5, GATE_MAX_DD: 0.10}
    result = evaluate(metrics, gates)
    assert result["passed"] is True
    assert result["failed_gates"] == []


def test_faz95_evaluate_fail_min_trades() -> None:
    """Metrics fail min_trades -> failed_gates includes min_trades."""
    metrics = {"total_fills": 2, "max_drawdown": 0.05}
    gates = {GATE_MIN_TRADES: 5, GATE_MAX_DD: 0.10}
    result = evaluate(metrics, gates)
    assert result["passed"] is False
    assert GATE_MIN_TRADES in result["failed_gates"]


def test_faz95_evaluate_fail_max_dd() -> None:
    """Metrics fail max_dd -> failed_gates includes max_dd."""
    metrics = {"total_fills": 10, "max_drawdown": 0.15}
    gates = {GATE_MIN_TRADES: 5, GATE_MAX_DD: 0.10}
    result = evaluate(metrics, gates)
    assert result["passed"] is False
    assert GATE_MAX_DD in result["failed_gates"]


def test_faz95_evaluate_deterministic() -> None:
    """Same metrics + same gates -> same result."""
    metrics = {"total_fills": 7, "max_drawdown": 0.08}
    gates = {GATE_MIN_TRADES: 5, GATE_MAX_DD: 0.10}
    r1 = evaluate(metrics, gates)
    r2 = evaluate(metrics, gates)
    assert r1 == r2


def test_faz95_run_gates_fail_exit2_and_artifacts(tmp_path: Path) -> None:
    """When gates fail: exit_code 2 and eval_report.json artifact written."""
    metrics = {"total_fills": 1, "max_drawdown": 0.20}
    gates = {GATE_MIN_TRADES: 5, GATE_MAX_DD: 0.10}
    passed, exit_code, artifacts = run_gates(metrics, gates, outdir=tmp_path, strict=True)
    assert passed is False
    assert exit_code == 2
    assert "eval_report_path" in artifacts
    report_path = Path(artifacts["eval_report_path"])
    assert report_path.is_file()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["passed"] is False
    assert report["failed_gates"]
    assert "details" in report
    assert "metrics" in report


def test_faz95_run_gates_pass_no_failure_artifact(tmp_path: Path) -> None:
    """When gates pass: exit_code 0, no failure report written (artifacts empty)."""
    metrics = {"total_fills": 10, "max_drawdown": 0.05}
    gates = {GATE_MIN_TRADES: 5, GATE_MAX_DD: 0.10}
    passed, exit_code, artifacts = run_gates(metrics, gates, outdir=tmp_path, strict=True)
    assert passed is True
    assert exit_code == 0
    assert artifacts.get("eval_report_path") is None or "eval_report_path" not in artifacts
    eval_report = tmp_path / "eval_report.json"
    assert not eval_report.exists()
