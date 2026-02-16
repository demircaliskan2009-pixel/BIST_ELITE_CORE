"""FAZ127: snapshots doctor --symbol bars_count lookback."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_faz127_doctor_symbol_bars_count(tmp_path: Path) -> None:
    """doctor --symbol X --day Y shows bars_count and lookback windows."""
    snap_root = tmp_path / "snapshots"
    for i, day in enumerate(["2099-01-01", "2099-01-02", "2099-01-03", "2099-01-04", "2099-01-05"]):
        day_dir = snap_root / day
        day_dir.mkdir(parents=True)
        syms = ["AAA", "BBB"] if i < 4 else ["BBB"]
        (day_dir / "snapshot.csv").write_text(
            "symbol,close\n" + "\n".join(f"{s},100" for s in syms) + "\n",
            encoding="utf-8",
        )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_project_root() / "src")
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snap_root)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "bist_core.cli",
            "data",
            "snapshots",
            "doctor",
            "--symbol",
            "AAA",
            "--day",
            "2099-01-04",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=30,
    )
    assert result.returncode == 0
    assert "bars_count: 4" in result.stdout
    assert "lookback_20" in result.stdout or "INSUFFICIENT" in result.stdout


def test_faz127_doctor_symbol_json(tmp_path: Path) -> None:
    """doctor --symbol --day --json outputs symbol_info with bars_count and lookback."""
    snap_root = tmp_path / "snapshots"
    for day in ["2099-01-01", "2099-01-02", "2099-01-03"]:
        day_dir = snap_root / day
        day_dir.mkdir(parents=True)
        (day_dir / "snapshot.csv").write_text(
            "symbol,close\nX,100\n",
            encoding="utf-8",
        )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_project_root() / "src")
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snap_root)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "bist_core.cli",
            "data",
            "snapshots",
            "doctor",
            "--symbol",
            "X",
            "--day",
            "2099-01-03",
            "--json",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=30,
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert "symbol_info" in data
    si = data["symbol_info"]
    assert si["symbol"] == "X"
    assert si["day"] == "2099-01-03"
    assert si["bars_count"] == 3
    assert si["lookback_20"] is False
    assert si["lookback_60"] is False
    assert si["lookback_120"] is False


def test_faz127_doctor_symbol_requires_day(tmp_path: Path) -> None:
    """doctor --symbol without --day returns error."""
    snap_root = tmp_path / "snapshots"
    (snap_root / "2099-01-01").mkdir(parents=True)
    (snap_root / "2099-01-01" / "snapshot.csv").write_text("symbol,close\nX,100\n", encoding="utf-8")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_project_root() / "src")
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snap_root)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "bist_core.cli",
            "data",
            "snapshots",
            "doctor",
            "--symbol",
            "X",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=30,
    )
    assert result.returncode == 2
    assert "day" in result.stderr.lower() or "day_required" in result.stdout
