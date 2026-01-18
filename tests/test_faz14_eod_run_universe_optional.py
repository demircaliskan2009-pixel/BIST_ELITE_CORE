from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_eod_run_universe_optional(tmp_path: Path) -> None:
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

    instruments_input = tmp_path / "instruments.jsonl"
    instruments_input.write_text(
        '{"symbol":"AAA","isin":"TRAAA","name":"AAA","status":"active","source":"offline_file","ts":"2099-01-01T00:00:00Z"}\n',
        encoding="utf-8",
    )
    ca_input = tmp_path / "actions.jsonl"
    ca_input.write_text(
        '{"symbol":"AAA","effective_date":"2099-01-01","kind":"symbol_change","old_symbol":"AAA","new_symbol":"CCC","ts":"2099-01-01T01:00:00Z","source":"offline_file"}\n',
        encoding="utf-8",
    )

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
            "--instruments-provider",
            "offline_file",
            "--instruments-input",
            str(instruments_input),
            "--ca-provider",
            "offline_file",
            "--ca-input",
            str(ca_input),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=env,
        check=False,
    )
    assert result.returncode == 0
    manifest = json.loads((outdir / "_pipeline_manifest.json").read_text(encoding="utf-8"))
    assert manifest.get("universe_manifest")
