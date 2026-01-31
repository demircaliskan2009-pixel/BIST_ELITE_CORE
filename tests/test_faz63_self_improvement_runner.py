"""
FAZ63: Self-improvement runner — walk-forward evaluation, model_report.json, champion selection by metrics gates.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from bist_core.services.self_improvement import (
    _select_champion,
    run_self_improvement,
)


def test_faz63_select_champion_deterministic() -> None:
    """Champion is highest mean_return among gates_passed; tie-break by lower dd then name."""
    results = [
        {"name": "a", "gates_passed": True, "mean_return": 0.1, "worst_max_drawdown": 0.05},
        {"name": "b", "gates_passed": True, "mean_return": 0.2, "worst_max_drawdown": 0.03},
        {"name": "c", "gates_passed": False, "mean_return": 0.3, "worst_max_drawdown": 0.0},
    ]
    assert _select_champion(results) == "b"


def test_faz63_select_champion_tie_break_lower_dd() -> None:
    """Same mean_return: prefer lower worst_max_drawdown."""
    results = [
        {"name": "high_dd", "gates_passed": True, "mean_return": 0.1, "worst_max_drawdown": 0.10},
        {"name": "low_dd", "gates_passed": True, "mean_return": 0.1, "worst_max_drawdown": 0.02},
    ]
    assert _select_champion(results) == "low_dd"


def test_faz63_select_champion_tie_break_name() -> None:
    """Same return and dd: lexicographic name."""
    results = [
        {"name": "beta", "gates_passed": True, "mean_return": 0.0, "worst_max_drawdown": 0.0},
        {"name": "alpha", "gates_passed": True, "mean_return": 0.0, "worst_max_drawdown": 0.0},
    ]
    assert _select_champion(results) == "alpha"


def test_faz63_select_champion_none_pass_returns_none() -> None:
    """When no candidate passes gates, champion is None."""
    results = [
        {"name": "x", "gates_passed": False, "mean_return": 0.5, "worst_max_drawdown": 0.0},
    ]
    assert _select_champion(results) is None


def test_faz63_run_writes_report_path(tmp_path: Path) -> None:
    """run_self_improvement writes outdir/reports/<day>/model_report.json and returns its path."""
    day = "2099-01-15"
    snap_dir = tmp_path / "snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)
    # Minimal data for 2-day window: need at least 2 days so one window exists
    for d in ["2099-01-01", "2099-01-02"]:
        (snap_dir / d).mkdir(exist_ok=True)
        (snap_dir / d / "snapshot.csv").write_text(
            "symbol,date,close\nAAA," + d + ",10\n",
            encoding="utf-8",
        )
    outdir = tmp_path / "out"
    report_path = run_self_improvement(
        day=day,
        date_from="2099-01-01",
        date_to="2099-01-02",
        snapshot_root=snap_dir,
        outdir=outdir,
        candidates=["equal_weight"],
        window_days=2,
        step_days=1,
    )
    assert report_path == outdir / "reports" / day / "model_report.json"
    assert report_path.is_file()


def test_faz63_report_schema(tmp_path: Path) -> None:
    """model_report.json has schema_version, day, candidates, champion, gates_passed."""
    day = "2099-01-16"
    snap_dir = tmp_path / "snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)
    for d in ["2099-01-01", "2099-01-02"]:
        (snap_dir / d).mkdir(exist_ok=True)
        (snap_dir / d / "snapshot.csv").write_text(
            "symbol,date,close\nX," + d + ",1\n",
            encoding="utf-8",
        )
    outdir = tmp_path / "out"
    run_self_improvement(
        day=day,
        date_from="2099-01-01",
        date_to="2099-01-02",
        snapshot_root=snap_dir,
        outdir=outdir,
        candidates=["equal_weight"],
        window_days=2,
        step_days=1,
    )
    report_path = outdir / "reports" / day / "model_report.json"
    data = json.loads(report_path.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert data["day"] == day
    assert "candidates" in data
    assert "champion" in data
    assert "gates_passed" in data
    assert len(data["candidates"]) >= 1
    c = data["candidates"][0]
    assert "name" in c
    assert "gates_passed" in c
    assert "mean_return" in c
    assert "worst_max_drawdown" in c


def test_faz63_multiple_candidates(tmp_path: Path) -> None:
    """Multiple candidates produce one result per candidate; champion is deterministic."""
    day = "2099-01-17"
    snap_dir = tmp_path / "snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)
    for d in ["2099-01-01", "2099-01-02"]:
        (snap_dir / d).mkdir(exist_ok=True)
        (snap_dir / d / "snapshot.csv").write_text(
            "symbol,date,close\nY," + d + ",2\n",
            encoding="utf-8",
        )
    outdir = tmp_path / "out"
    run_self_improvement(
        day=day,
        date_from="2099-01-01",
        date_to="2099-01-02",
        snapshot_root=snap_dir,
        outdir=outdir,
        candidates=["equal_weight", "deny_all"],
        window_days=2,
        step_days=1,
    )
    report_path = outdir / "reports" / day / "model_report.json"
    data = json.loads(report_path.read_text(encoding="utf-8"))
    assert len(data["candidates"]) == 2
    names = {c["name"] for c in data["candidates"]}
    assert names == {"deny_all", "equal_weight"}
    assert data["champion"] in ("deny_all", "equal_weight") or data["champion"] is None
