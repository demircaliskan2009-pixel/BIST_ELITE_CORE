from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_replay_strict_failclosed_on_day_error(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")

    snapshot_root = tmp_path / "data" / "eod" / "snapshots"
    day = "2025-01-15"
    outdir = tmp_path / "replay_out"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "bist_core.cli",
            "eod",
            "replay",
            "--from",
            day,
            "--to",
            day,
            "--snapshot-root",
            str(snapshot_root),
            "--outdir",
            str(outdir),
            "--strict",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=env,
        check=False,
    )

    assert result.returncode == 2
    manifest = json.loads((outdir / "_replay_manifest.json").read_text(encoding="utf-8"))
    assert manifest["summary"]["error"] >= 1
