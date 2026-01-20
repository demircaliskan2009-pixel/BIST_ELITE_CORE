from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_batch_dry_run_plans_days(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")

    snapshot_root = tmp_path / "data" / "eod" / "snapshots"
    for day in ["2099-01-01", "2099-01-02"]:
        day_dir = snapshot_root / day
        day_dir.mkdir(parents=True)
        (day_dir / "snapshot.csv").write_text(
            "symbol,close\nAAA,1.0\n",
            encoding="utf-8",
        )
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
            "2099-01-02",
            "--outdir",
            str(outdir),
            "--ignore-calendar",
            "--dry-run",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=env,
        check=False,
    )
    assert result.returncode == 0
    manifest = json.loads((outdir / "_index_manifest.json").read_text(encoding="utf-8"))
    statuses = [d["status"] for d in manifest["days"]]
    assert statuses == ["planned_run", "planned_run"]
    assert not (outdir / "2099-01-01").exists()
