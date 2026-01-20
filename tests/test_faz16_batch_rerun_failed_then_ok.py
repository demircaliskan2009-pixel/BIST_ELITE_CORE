from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_batch_rerun_failed_then_ok(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")

    snapshot_root = tmp_path / "data" / "eod" / "snapshots"
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snapshot_root)

    outdir = tmp_path / "data" / "eod" / "batch"
    first = subprocess.run(
        [
            sys.executable,
            "-m",
            "bist_core.cli",
            "eod",
            "batch",
            "--from",
            "2099-01-01",
            "--to",
            "2099-01-01",
            "--outdir",
            str(outdir),
            "--ignore-calendar",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=env,
        check=False,
    )
    assert first.returncode == 0
    manifest = json.loads((outdir / "_index_manifest.json").read_text(encoding="utf-8"))
    assert manifest["days"][0]["status"] == "error"

    day_dir = snapshot_root / "2099-01-01"
    day_dir.mkdir(parents=True)
    (day_dir / "snapshot.csv").write_text(
        "symbol,close\nAAA,1.0\n",
        encoding="utf-8",
    )

    second = subprocess.run(
        [
            sys.executable,
            "-m",
            "bist_core.cli",
            "eod",
            "batch",
            "--from",
            "2099-01-01",
            "--to",
            "2099-01-01",
            "--outdir",
            str(outdir),
            "--ignore-calendar",
            "--resume",
            "--rerun-failed",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=env,
        check=False,
    )
    assert second.returncode == 0
    manifest_second = json.loads((outdir / "_index_manifest.json").read_text(encoding="utf-8"))
    assert manifest_second["days"][0]["status"] == "ok"
    assert (outdir / "2099-01-01" / "_pipeline_manifest.json").exists()
