from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_eod_run_ca_optional(tmp_path: Path) -> None:
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
    assert manifest.get("corporate_actions_manifest") is None

    actions_input = tmp_path / "actions.jsonl"
    actions_input.write_text(
        '{"symbol":"AAA","effective_date":"2099-01-02","kind":"split","ratio":2,"ts":"2099-01-01T10:00:00Z","source":"offline_file"}\n',
        encoding="utf-8",
    )
    ca_outdir = tmp_path / "ca_out" / "2099-01-01"
    result_with = subprocess.run(
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
            "--ca-provider",
            "offline_file",
            "--ca-input",
            str(actions_input),
            "--ca-outdir",
            str(ca_outdir),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=env,
        check=False,
    )
    assert result_with.returncode == 0
    manifest_with = json.loads((outdir / "_pipeline_manifest.json").read_text(encoding="utf-8"))
    assert manifest_with.get("corporate_actions_manifest")
