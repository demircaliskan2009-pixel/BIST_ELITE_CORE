"""FAZ137: Gates outcomes section — PASS/FAIL per gate with reasons in JSON."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_faz137_gates_in_ask_artifact(tmp_path: Path) -> None:
    """Ask artifact includes gates with outcome PASS/FAIL and reason."""
    snap_dir = tmp_path / "snapshots" / "2025-01-15"
    snap_dir.mkdir(parents=True)
    (snap_dir / "snapshot.csv").write_text("symbol,close\nAKBNK,50.0\n", encoding="utf-8")
    out_dir = tmp_path / "out"

    env = os.environ.copy()
    env["BIST_CORE_SNAPSHOT_DIR"] = str(tmp_path / "snapshots")
    env.pop("BIST_CORE_ALLOW_NETWORK", None)

    r = subprocess.run(
        [
            sys.executable, "-m", "bist_core.cli", "ask", "AKBNK",
            "--day", "2025-01-15", "--out", str(out_dir),
        ],
        cwd=str(_repo_root()),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=30,
    )
    assert r.returncode == 0, r.stderr
    artifact_path = out_dir / "2025-01-15" / "AKBNK.json"
    assert artifact_path.is_file(), f"Artifact not written: {artifact_path}"
    out = json.loads(artifact_path.read_text(encoding="utf-8"))
    gates = out.get("gates", {})
    assert gates, "Artifact must include gates"
    for gate_name, gate_data in gates.items():
        assert "outcome" in gate_data
        assert gate_data["outcome"] in ("PASS", "FAIL")
        assert "reason" in gate_data
