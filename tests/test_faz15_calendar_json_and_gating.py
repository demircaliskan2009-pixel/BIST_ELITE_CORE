from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_calendar_json_and_gating(tmp_path: Path) -> None:
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

    calendar_file = tmp_path / "calendar.json"
    calendar_file.write_text(
        json.dumps({"holidays": ["2099-01-01"]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    outdir = tmp_path / "data" / "eod" / "runs" / "2099-01-01"
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
            "--calendar-file",
            str(calendar_file),
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
    manifest = json.loads((outdir / "_pipeline_manifest.json").read_text(encoding="utf-8"))
    calendar_stage = manifest.get("stages", {}).get("calendar", {})
    assert calendar_stage.get("errors", 0) > 0
    assert not (outdir / "advice" / "2099-01-01" / "advice_records.jsonl").exists()
    assert not (outdir / "dossiers").exists()

    outdir_ignore = tmp_path / "data" / "eod" / "runs" / "2099-01-01-ignore"
    result_ignore = subprocess.run(
        [
            sys.executable,
            "-m",
            "bist_core.cli",
            "eod",
            "run",
            "--day",
            "2099-01-01",
            "--outdir",
            str(outdir_ignore),
            "--calendar-file",
            str(calendar_file),
            "--ignore-calendar",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=env,
        check=False,
    )
    assert result_ignore.returncode == 0
    assert (outdir_ignore / "advice" / "2099-01-01" / "advice_records.jsonl").exists()
    assert (outdir_ignore / "dossiers").exists()
