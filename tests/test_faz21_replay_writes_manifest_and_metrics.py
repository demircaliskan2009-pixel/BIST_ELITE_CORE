from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_replay_writes_manifest_and_metrics(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")

    snapshot_root = tmp_path / "data" / "eod" / "snapshots"
    day_a = "2025-01-15"
    day_b = "2025-01-16"
    for day in (day_a, day_b):
        day_dir = snapshot_root / day
        day_dir.mkdir(parents=True, exist_ok=True)
        (day_dir / "snapshot.csv").write_text(
            "symbol,close\nAAA,1.0\n",
            encoding="utf-8",
        )

    outdir = tmp_path / "replay_out"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "bist_core.cli",
            "eod",
            "replay",
            "--from",
            day_a,
            "--to",
            day_b,
            "--snapshot-root",
            str(snapshot_root),
            "--outdir",
            str(outdir),
            "--emit-orders",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=env,
        check=False,
    )

    assert result.returncode == 0
    replay_manifest = json.loads((outdir / "_replay_manifest.json").read_text(encoding="utf-8"))
    metrics = json.loads((outdir / "metrics.json").read_text(encoding="utf-8"))
    assert replay_manifest["schema_version"] == 1
    assert replay_manifest["summary"]["total"] >= 1
    assert replay_manifest["summary"]["ok"] >= 1
    assert metrics["schema_version"] == 1
    assert metrics["total_days"] >= 1
