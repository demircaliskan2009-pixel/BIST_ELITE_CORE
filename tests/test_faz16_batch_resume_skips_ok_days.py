from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_batch_resume_skips_ok_days(tmp_path: Path) -> None:
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
            "2099-01-02",
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
    manifest_paths = {day: (outdir / day / "_pipeline_manifest.json") for day in ["2099-01-01", "2099-01-02"]}
    before_contents = {day: path.read_text(encoding="utf-8") for day, path in manifest_paths.items()}

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
            "2099-01-02",
            "--outdir",
            str(outdir),
            "--ignore-calendar",
            "--resume",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=env,
        check=False,
    )
    assert second.returncode == 0
    index_manifest = json.loads((outdir / "_index_manifest.json").read_text(encoding="utf-8"))
    assert index_manifest["schema_version"] == 2
    assert index_manifest["summary"]["skipped_ok_existing"] == 2
    assert index_manifest["summary"]["ran"] == 0
    for day, path in manifest_paths.items():
        assert path.read_text(encoding="utf-8") == before_contents[day]
