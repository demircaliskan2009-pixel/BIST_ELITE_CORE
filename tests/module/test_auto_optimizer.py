"""Deterministic auto_optimizer state transitions."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from bist_core.validation.auto_optimizer import apply_fixes, load_state, run_step


def test_apply_fake_edge_increases_min_fill() -> None:
    st = apply_fixes("FAKE_EDGE", load_state())
    assert float(st["BIST_REALISM_MIN_FILL_RATIO"]) > 0.22


def test_apply_unstable_reduces_risk_combined() -> None:
    st = apply_fixes("UNSTABLE_SYSTEM", load_state())
    assert float(st["BIST_RISK_COMBINED_MULT"]) < 1.0


def test_run_step_writes_report_on_success(tmp_path: Path, monkeypatch) -> None:
    from bist_core.validation import auto_optimizer as ao

    monkeypatch.setattr(ao, "_TOOLS", tmp_path)
    monkeypatch.setattr(ao, "_STATE_PATH", tmp_path / "optimizer_state.json")
    monkeypatch.setattr(ao, "_ENV_PATH", tmp_path / "optimizer_env.ps1")
    monkeypatch.setattr(ao, "_HISTORY_PATH", tmp_path / "optimizer_history.json")
    monkeypatch.setattr(ao, "_FINAL_REPORT", tmp_path / "auto_optimize_report.json")

    analysis = {
        "diagnosis": {
            "SYSTEM_TYPE": "REAL_EDGE",
            "EDGE_CONFIDENCE": 0.8,
            "MAIN_WEAKNESS": "none",
        },
        "failure_flags": [],
        "derived_metrics": {},
    }
    p = tmp_path / "a.json"
    p.write_text(json.dumps(analysis), encoding="utf-8")
    code = run_step(p, 1, 3)
    assert code == 0
    assert (tmp_path / "auto_optimize_report.json").is_file()
