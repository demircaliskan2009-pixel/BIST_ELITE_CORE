from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_eod_batch_calendar_skip_and_strict(tmp_path: Path) -> None:
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

    calendar_file = tmp_path / "calendar.json"
    calendar_file.write_text(
        json.dumps(
            {
                "holidays": ["2099-01-01"],
                "trading_days": ["2099-01-02"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

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
    assert result.returncode == 0
    index_manifest = json.loads((outdir / "_index_manifest.json").read_text(encoding="utf-8"))
    day_map = {d["day"]: d for d in index_manifest["days"]}
    assert day_map["2099-01-01"]["status"] == "skipped_calendar"
    assert (outdir / "2099-01-01").exists() is False
    assert day_map["2099-01-02"]["status"] == "ok"
    assert (outdir / "2099-01-02" / "advice" / "2099-01-02" / "advice_records.jsonl").exists()

    outdir_error = tmp_path / "data" / "eod" / "batch_error"
    result_error = subprocess.run(
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
            str(outdir_error),
            "--calendar-file",
            str(tmp_path / "missing_calendar.json"),
            "--strict",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=env,
        check=False,
    )
    assert result_error.returncode == 2
    index_error = json.loads(
        (outdir_error / "_index_manifest.json").read_text(encoding="utf-8")
    )
    assert index_error["errors"]
