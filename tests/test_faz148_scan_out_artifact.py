"""FAZ148: Scan --out artifact — save ranked list JSON to file."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_faz148_scan_out_writes_json(tmp_path: Path) -> None:
    """Scan --out writes ranked JSON to out/day/scan.json."""
    snap_dir = tmp_path / "snapshots" / "2025-01-15"
    snap_dir.mkdir(parents=True)
    (snap_dir / "snapshot.csv").write_text("symbol,close\nAKBNK,50.0\nGARAN,100.0\n", encoding="utf-8")
    out_dir = tmp_path / "out"

    env = os.environ.copy()
    env["BIST_CORE_SNAPSHOT_DIR"] = str(tmp_path / "snapshots")
    env.pop("BIST_CORE_ALLOW_NETWORK", None)

    r = subprocess.run(
        [
            sys.executable, "-m", "bist_core.cli", "scan",
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
    artifact_path = out_dir / "2025-01-15" / "scan.json"
    assert artifact_path.is_file(), f"Expected {artifact_path}"
    out = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert "schema_version" in out
    assert "day" in out
    assert "ranked" in out
    assert out["day"] == "2025-01-15"
