from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_batch_max_failures_stops_early(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")

    snapshot_root = tmp_path / "data" / "eod" / "snapshots"
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snapshot_root)

    outdir = tmp_path / "data" / "eod" / "batch"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "bist_core.cli",
            "eod",
            "batch",
            "--from",
            "2099-01-01",
            "--to",
            "2099-01-03",
            "--outdir",
            str(outdir),
            "--ignore-calendar",
            "--max-failures",
            "1",
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
    manifest = json.loads((outdir / "_index_manifest.json").read_text(encoding="utf-8"))
    assert manifest["stopped_early"] is True
    assert manifest["stop_reason"] == "max_failures_reached"
    assert len(manifest["days"]) == 3
    assert manifest["days"][0]["status"] == "error"
    assert manifest["days"][1]["status"] == "not_run"
    assert manifest["summary"]["errors"] >= 1
    assert manifest["summary"]["total"] == 3
