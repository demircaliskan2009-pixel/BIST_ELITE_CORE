from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_dossier_includes_events(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")

    snapshot_root = tmp_path / "data" / "eod" / "snapshots"
    day_dir = snapshot_root / "2099-01-01"
    day_dir.mkdir(parents=True)
    (day_dir / "snapshot.csv").write_text(
        "symbol,close\nAAA,\n",
        encoding="utf-8",
    )
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snapshot_root)

    events_root = tmp_path / "data" / "events"
    events_day = events_root / "2099-01-01"
    events_day.mkdir(parents=True)
    (events_day / "events.jsonl").write_text(
        '{"symbol":"AAA","ts":"2099-01-01T10:00:00","kind":"KAP","title":"AAA Event"}\n',
        encoding="utf-8",
    )
    env["BIST_CORE_EVENTS_DIR"] = str(events_root)

    outdir = tmp_path / "out"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "bist_core.cli",
            "dossier",
            "build",
            "--day",
            "2099-01-01",
            "--all",
            "--outdir",
            str(outdir),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=env,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads((outdir / "AAA.json").read_text(encoding="utf-8"))
    assert "events" in payload
    assert payload["events"]
    assert payload["events"][0]["title"] == "AAA Event"
