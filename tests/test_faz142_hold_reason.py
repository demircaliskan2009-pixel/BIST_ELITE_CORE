"""FAZ142: HOLD reason coverage — artifact has reason and next_action when HOLD."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_faz142_hold_artifact_has_reason_and_next_action(tmp_path: Path) -> None:
    """HOLD path (1 bar) produces artifact with reason and next_action."""
    snap_root = tmp_path / "snapshots"
    day_dir = snap_root / "2099-01-01"
    day_dir.mkdir(parents=True)
    (day_dir / "snapshot.csv").write_text("symbol,close\nBBB,100.0\n", encoding="utf-8")
    out_dir = tmp_path / "out" / "ask"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_project_root() / "src")
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snap_root)

    result = subprocess.run(
        [sys.executable, "-m", "bist_core.cli", "ask", "BBB", "--day", "2099-01-01", "--out", str(out_dir)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=30,
    )
    assert result.returncode == 0
    artifact = out_dir / "2099-01-01" / "BBB.json"
    assert artifact.exists()
    data = json.loads(artifact.read_text(encoding="utf-8"))
    assert data["decision_raw"] == "HOLD"
    assert "reason" in data
    assert data["reason"] == "InsufficientHistory"
    assert "next_action" in data
    assert "Daha fazla" in data["next_action"] or len(data["next_action"]) > 0
