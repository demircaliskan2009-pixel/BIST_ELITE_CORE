from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_cli_eod_run_smoke(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")

    snapshot_root = tmp_path / "data" / "eod" / "snapshots"
    day_dir = snapshot_root / "2099-01-01"
    day_dir.mkdir(parents=True)
    (day_dir / "snapshot.csv").write_text(
        "symbol,close\nAAA,\nBBB,\nCCC,\n",
        encoding="utf-8",
    )
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snapshot_root)

    outdir = tmp_path / "out"
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
    manifest_path = outdir / "_pipeline_manifest.json"
    assert manifest_path.exists()
    _ = json.loads(manifest_path.read_text(encoding="utf-8"))

    advice_path = outdir / "advice.jsonl"
    assert advice_path.exists()
    lines = advice_path.read_text(encoding="utf-8").splitlines()
    assert lines
    _ = json.loads(lines[0])

    dossier_dir = outdir / "dossiers"
    assert dossier_dir.exists()
    assert list(dossier_dir.glob("*.json"))
