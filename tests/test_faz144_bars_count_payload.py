"""FAZ144: bars_count and lookback_required in advice JSON."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_faz144_hold_artifact_has_bars_count_and_lookback(tmp_path: Path) -> None:
    """HOLD path (1 bar) produces artifact with bars_count and lookback_required."""
    snap_root = tmp_path / "snapshots"
    day_dir = snap_root / "2099-01-03"
    day_dir.mkdir(parents=True)
    (day_dir / "snapshot.csv").write_text("symbol,close\nEEE,100.0\n", encoding="utf-8")
    out_dir = tmp_path / "out" / "ask"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_project_root() / "src")
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snap_root)

    result = subprocess.run(
        [sys.executable, "-m", "bist_core.cli", "ask", "EEE", "--day", "2099-01-03", "--out", str(out_dir)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=30,
    )
    assert result.returncode == 0
    artifact = out_dir / "2099-01-03" / "EEE.json"
    assert artifact.exists()
    data = json.loads(artifact.read_text(encoding="utf-8"))
    assert data["decision_raw"] == "HOLD"
    assert "bars_count" in data
    assert data["bars_count"] == 1
    assert "lookback_required" in data
    assert data["lookback_required"] >= 20
