"""FAZ122: CLI data snapshots doctor - root/day/symbol coverage."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_faz122_snapshots_doctor_day_and_symbol(tmp_path: Path) -> None:
    """data snapshots doctor shows day and symbol in output."""
    snap_root = tmp_path / "snapshots"
    day_dir = snap_root / "2099-01-01"
    day_dir.mkdir(parents=True)
    (day_dir / "snapshot.csv").write_text(
        "symbol,close\nAAA,100.0\nBBB,200.0\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_project_root() / "src")
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snap_root)

    result = subprocess.run(
        [sys.executable, "-m", "bist_core.cli", "data", "snapshots", "doctor"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=30,
    )
    assert result.returncode == 0
    assert "2099-01-01" in result.stdout
    assert "AAA" in result.stdout or "2 symbols" in result.stdout


def test_faz122_snapshots_doctor_json(tmp_path: Path) -> None:
    """data snapshots doctor --json outputs valid schema with expected keys."""
    snap_root = tmp_path / "snapshots"
    day_dir = snap_root / "2099-01-01"
    day_dir.mkdir(parents=True)
    (day_dir / "snapshot.csv").write_text(
        "symbol,close\nAAA,100.0\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_project_root() / "src")
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snap_root)

    result = subprocess.run(
        [sys.executable, "-m", "bist_core.cli", "data", "snapshots", "doctor", "--json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=30,
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert "root" in data
    assert "days" in data
    assert "symbols_by_day" in data
    assert "coverage_summary" in data
    assert data["days"] == ["2099-01-01"]
    assert "AAA" in data["symbols_by_day"].get("2099-01-01", [])
