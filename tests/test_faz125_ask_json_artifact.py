"""FAZ125: Ask output template + JSON artifact saved and path printed."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_faz125_ask_json_artifact(tmp_path: Path) -> None:
    """ask writes JSON artifact and prints Artifact path."""
    snap_root = tmp_path / "snapshots"
    day_dir = snap_root / "2099-01-01"
    day_dir.mkdir(parents=True)
    (day_dir / "snapshot.csv").write_text(
        "symbol,close\nAAA,100.0\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "out" / "ask"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_project_root() / "src")
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snap_root)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "bist_core.cli",
            "ask",
            "AAA",
            "--day",
            "2099-01-01",
            "--out",
            str(out_dir),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=30,
    )
    assert result.returncode == 0
    assert "Artifact:" in result.stdout
    artifact_path = out_dir / "2099-01-01" / "AAA.json"
    assert artifact_path.exists()
    data = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert "symbol" in data
    assert "day" in data
    assert "decision_raw" in data
    assert "Decision" in data or "decision_raw" in data
