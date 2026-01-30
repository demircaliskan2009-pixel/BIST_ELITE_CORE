"""FAZ52: Manifest timestamps are timezone-aware UTC; format YYYY-MM-DDTHH:MM:SS.mmmZ; parseable."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def _parse_utc_iso(s: str) -> datetime:
    """Parse ISO timestamp ending with Z as UTC."""
    normalized = s.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)


def test_manifest_started_finished_utc_endswith_z_and_parseable(tmp_path: Path) -> None:
    """started_at_utc and finished_at_utc end with Z and are parseable as UTC."""
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")
    day = "2099-02-01"
    snap_dir = tmp_path / "snap"
    (snap_dir / day).mkdir(parents=True)
    (snap_dir / day / "snapshot.csv").write_text(
        "symbol,date,close\nX,2099-02-01,100\n",
        encoding="utf-8",
    )
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snap_dir)
    outdir = tmp_path / "out"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "bist_core.cli",
            "eod",
            "run",
            "--day",
            day,
            "--outdir",
            str(outdir),
        ],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    manifest_path = outdir / day / "pipeline_manifest.json"
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    started = manifest.get("started_at_utc", "")
    finished = manifest.get("finished_at_utc", "")
    assert started.endswith("Z"), f"started_at_utc must end with Z: {started!r}"
    assert finished.endswith("Z"), f"finished_at_utc must end with Z: {finished!r}"
    dt_start = _parse_utc_iso(started)
    dt_finish = _parse_utc_iso(finished)
    assert dt_start.tzinfo is not None
    assert dt_finish.tzinfo is not None
    assert dt_finish >= dt_start
