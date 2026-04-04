"""FAZ124: CLI scan --interactive wizard + ranked output + drill-down."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_faz124_scan_non_interactive_ranked(tmp_path: Path) -> None:
    """scan with args produces ranked list and drill-down commands."""
    snap_root = tmp_path / "snapshots"
    day_dir = snap_root / "2099-01-01"
    day_dir.mkdir(parents=True)
    (day_dir / "snapshot.csv").write_text(
        "symbol,close\nAAA,100.0\nBBB,200.0\nCCC,150.0\n",
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
            "scan",
            "--day",
            "2099-01-01",
            "--top-n",
            "2",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=60,
    )
    assert result.returncode == 0
    assert "Scan 2099-01-01" in result.stdout
    assert "Drill-down:" in result.stdout
    assert "python -m bist_core.cli ask" in result.stdout
    assert "2099-01-01" in result.stdout
    assert "--interactive" in result.stdout
