from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _run_replay(snapshot_root: Path, outdir: Path, day: str) -> None:
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
            "--orders-strategy",
            "deny_all",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=env,
        check=False,
    )
    assert result.returncode == 0


def test_replay_scorecard_written_and_deterministic(tmp_path: Path) -> None:
    snapshot_root = tmp_path / "data" / "eod" / "snapshots"
    day = "2025-02-03"
    day_dir = snapshot_root / day
    day_dir.mkdir(parents=True, exist_ok=True)
    (day_dir / "snapshot.csv").write_text(
        "symbol,close\nAAA,1.0\n",
        encoding="utf-8",
    )

    outdir_a = tmp_path / "out_a"
    outdir_b = tmp_path / "out_b"
    _run_replay(snapshot_root, outdir_a, day)
    _run_replay(snapshot_root, outdir_b, day)

    scorecard_a = json.loads((outdir_a / "scorecard.json").read_text(encoding="utf-8"))
    scorecard_b = json.loads((outdir_b / "scorecard.json").read_text(encoding="utf-8"))
    assert scorecard_a == scorecard_b
