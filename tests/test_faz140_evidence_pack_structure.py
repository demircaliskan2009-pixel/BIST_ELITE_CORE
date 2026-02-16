"""FAZ140: Evidence pack structure — source and hash in artifact."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_faz140_evidence_has_source_and_hash_when_snapshot_exists(tmp_path: Path) -> None:
    """Ask artifact Evidence includes source and source_sha256 when snapshot exists."""
    snap_root = tmp_path / "snapshots"
    day_dir = snap_root / "2099-01-01"
    day_dir.mkdir(parents=True)
    (day_dir / "snapshot.csv").write_text("symbol,close\nAAA,100.0\n", encoding="utf-8")
    out_dir = tmp_path / "out" / "ask"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_project_root() / "src")
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snap_root)

    result = subprocess.run(
        [sys.executable, "-m", "bist_core.cli", "ask", "AAA", "--day", "2099-01-01", "--out", str(out_dir)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=30,
    )
    assert result.returncode == 0
    artifact = out_dir / "2099-01-01" / "AAA.json"
    assert artifact.exists()
    data = json.loads(artifact.read_text(encoding="utf-8"))
    ev = data.get("Evidence", {})
    assert "source" in ev
    assert "2099-01-01" in ev["source"] or "snapshot.csv" in ev["source"]
    assert "source_sha256" in ev
    assert len(ev["source_sha256"]) == 64
