"""FAZ143: Advice artifact content hash — content_sha256 for reproducibility."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_faz143_artifact_has_content_sha256(tmp_path: Path) -> None:
    """Ask artifact includes content_sha256 (64-char hex); excludes generated_at from hash."""
    snap_root = tmp_path / "snapshots"
    day_dir = snap_root / "2099-01-01"
    day_dir.mkdir(parents=True)
    (day_dir / "snapshot.csv").write_text("symbol,close\nCCC,100.0\n", encoding="utf-8")
    out_dir = tmp_path / "out" / "ask"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_project_root() / "src")
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snap_root)

    result = subprocess.run(
        [sys.executable, "-m", "bist_core.cli", "ask", "CCC", "--day", "2099-01-01", "--out", str(out_dir)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=30,
    )
    assert result.returncode == 0
    artifact = out_dir / "2099-01-01" / "CCC.json"
    assert artifact.exists()
    data = json.loads(artifact.read_text(encoding="utf-8"))
    assert "content_sha256" in data
    h = data["content_sha256"]
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


def test_faz143_content_hash_stable_same_inputs(tmp_path: Path) -> None:
    """Same inputs produce same content_sha256 across runs (deterministic)."""
    snap_root = tmp_path / "snapshots"
    day_dir = snap_root / "2099-01-02"
    day_dir.mkdir(parents=True)
    (day_dir / "snapshot.csv").write_text("symbol,close\nDDD,50.0\n", encoding="utf-8")
    out_dir = tmp_path / "out" / "ask"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_project_root() / "src")
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snap_root)

    def run_ask() -> str:
        subprocess.run(
            [sys.executable, "-m", "bist_core.cli", "ask", "DDD", "--day", "2099-01-02", "--out", str(out_dir)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
            timeout=30,
        )
        data = json.loads((out_dir / "2099-01-02" / "DDD.json").read_text(encoding="utf-8"))
        return data["content_sha256"]

    h1 = run_ask()
    h2 = run_ask()
    assert h1 == h2, "content_sha256 must be deterministic for same inputs"
