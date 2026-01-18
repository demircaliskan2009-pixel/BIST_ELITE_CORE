from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_eod_run_events_optional(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")

    snapshot_root = tmp_path / "data" / "eod" / "snapshots"
    day_dir = snapshot_root / "2099-01-01"
    day_dir.mkdir(parents=True)
    (day_dir / "snapshot.csv").write_text(
        "symbol,close\nAAA,1.0\n",
        encoding="utf-8",
    )
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snapshot_root)

    events_input = tmp_path / "events_input.jsonl"
    events_input.write_text(
        '{"symbol":"AAA","ts":"2099-01-01T10:00:00Z","kind":"KAP","title":"A1"}\n',
        encoding="utf-8",
    )

    events_outdir = tmp_path / "events_out" / "2099-01-01"
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
            "--events-provider",
            "offline_file",
            "--events-input",
            str(events_input),
            "--events-outdir",
            str(events_outdir),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=env,
        check=False,
    )

    assert result.returncode == 0
    pipeline_manifest = json.loads(
        (outdir / "_pipeline_manifest.json").read_text(encoding="utf-8")
    )
    assert pipeline_manifest["stages"]["events"]["errors"] == 0
    assert (events_outdir / "events.jsonl").exists()
    assert (events_outdir / "_manifest.json").exists()
