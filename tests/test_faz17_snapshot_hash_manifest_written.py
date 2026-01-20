from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from bist_core.services import snapshot_integrity


def test_snapshot_hash_manifest_written(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")

    snapshot_root = tmp_path / "data" / "eod" / "snapshots"
    day_dir = snapshot_root / "2099-01-01"
    day_dir.mkdir(parents=True)
    snapshot_path = day_dir / "snapshot.csv"
    snapshot_path.write_text(
        "symbol,close\nAAA,1.0\n",
        encoding="utf-8",
    )
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snapshot_root)

    outdir = tmp_path / "run_out"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "bist_core.cli",
            "eod",
            "run",
            "--day",
            "2099-01-01",
            "--outdir",
            str(outdir),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=env,
        check=False,
    )
    assert result.returncode == 0

    hash_path = day_dir / "_snapshot_hash.json"
    assert hash_path.exists()
    payload = json.loads(hash_path.read_text(encoding="utf-8"))
    assert payload["sha256"] == snapshot_integrity.compute_sha256(snapshot_path)
