"""FAZ147: Scan scoring rationale — 1-line rationale per ranked symbol from deterministic signals."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_faz147_scan_rationale_per_symbol(tmp_path: Path) -> None:
    """Scan ranked output has rationale per symbol."""
    snap_dir = tmp_path / "snapshots" / "2025-01-15"
    snap_dir.mkdir(parents=True)
    (snap_dir / "snapshot.csv").write_text("symbol,close\nAKBNK,50.0\nGARAN,100.0\n", encoding="utf-8")

    env = os.environ.copy()
    env["BIST_CORE_SNAPSHOT_DIR"] = str(tmp_path / "snapshots")
    env.pop("BIST_CORE_ALLOW_NETWORK", None)

    r = subprocess.run(
        [sys.executable, "-m", "bist_core.cli", "scan", "--day", "2025-01-15", "--json"],
        cwd=str(_repo_root()),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=30,
    )
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    for item in out.get("ranked", []):
        assert "rationale" in item
        assert isinstance(item["rationale"], str)
        assert len(item["rationale"]) <= 80 or "\n" not in item["rationale"]
