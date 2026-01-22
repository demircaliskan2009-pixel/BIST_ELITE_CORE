from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _run_replay(tmp_path: Path, snapshot_root: Path, outdir: Path, day: str) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")

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


def _normalize_manifest(payload: dict) -> dict:
    payload = json.loads(json.dumps(payload))
    payload["outdir"] = "<outdir>"
    payload["summary"]["runtime_ms"] = 0
    for day_entry in payload.get("days", []):
        day_entry["pipeline_manifest_path"] = "<path>"
    return payload


def test_replay_deterministic(tmp_path: Path) -> None:
    snapshot_root = tmp_path / "data" / "eod" / "snapshots"
    day = "2025-01-15"
    day_dir = snapshot_root / day
    day_dir.mkdir(parents=True, exist_ok=True)
    (day_dir / "snapshot.csv").write_text(
        "symbol,close\nAAA,1.0\n",
        encoding="utf-8",
    )

    outdir_a = tmp_path / "out_a"
    outdir_b = tmp_path / "out_b"
    _run_replay(tmp_path, snapshot_root, outdir_a, day)
    _run_replay(tmp_path, snapshot_root, outdir_b, day)

    manifest_a = json.loads((outdir_a / "_replay_manifest.json").read_text(encoding="utf-8"))
    manifest_b = json.loads((outdir_b / "_replay_manifest.json").read_text(encoding="utf-8"))
    metrics_a = json.loads((outdir_a / "metrics.json").read_text(encoding="utf-8"))
    metrics_b = json.loads((outdir_b / "metrics.json").read_text(encoding="utf-8"))

    assert _normalize_manifest(manifest_a) == _normalize_manifest(manifest_b)
    assert metrics_a == metrics_b
