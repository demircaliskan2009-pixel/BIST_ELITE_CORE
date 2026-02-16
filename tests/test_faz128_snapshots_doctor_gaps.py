"""FAZ128: snapshots doctor missing days in range."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_faz128_doctor_missing_days(tmp_path: Path) -> None:
    """doctor shows missing days when gaps exist in range."""
    snap_root = tmp_path / "snapshots"
    for day in ["2099-01-01", "2099-01-03", "2099-01-05"]:
        (snap_root / day).mkdir(parents=True)
        (snap_root / day / "snapshot.csv").write_text("symbol,close\nX,100\n", encoding="utf-8")
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
    assert "missing_days" in result.stdout or "01-02" in result.stdout or "2099-01-02" in result.stdout


def test_faz128_doctor_missing_days_json(tmp_path: Path) -> None:
    """doctor --json includes missing_days when gaps exist."""
    snap_root = tmp_path / "snapshots"
    for day in ["2099-01-01", "2099-01-03"]:
        (snap_root / day).mkdir(parents=True)
        (snap_root / day / "snapshot.csv").write_text("symbol,close\nX,100\n", encoding="utf-8")
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
    assert "missing_days" in data.get("coverage_summary", data)
    missing = data.get("coverage_summary", {}).get("missing_days", data.get("missing_days", []))
    assert "2099-01-02" in missing


def test_faz128_doctor_no_gaps(tmp_path: Path) -> None:
    """doctor shows empty missing_days when no gaps."""
    snap_root = tmp_path / "snapshots"
    for day in ["2099-01-01", "2099-01-02", "2099-01-03"]:
        (snap_root / day).mkdir(parents=True)
        (snap_root / day / "snapshot.csv").write_text("symbol,close\nX,100\n", encoding="utf-8")
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
    missing = data.get("coverage_summary", {}).get("missing_days", [])
    assert missing == []
