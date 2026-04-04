from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def test_batch_deep_audit_missing_artifact(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")

    snapshot_root = tmp_path / "data" / "eod" / "snapshots"
    day_dir = snapshot_root / "2099-01-01"
    day_dir.mkdir(parents=True)
    snapshot_path = day_dir / "snapshot.csv"
    snapshot_path.write_text(
        "symbol,close\nAAA,1.0\n",
        encoding="utf-8",
    )
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snapshot_root)

    outdir = tmp_path / "runs"
    run = subprocess.run(
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
    assert run.returncode == 0

    shutil.rmtree(outdir / "2099-01-01" / "dossiers")

    audit = subprocess.run(
        [
            sys.executable,
            "-m",
            "bist_core.cli",
            "eod",
            "batch",
            "--audit",
            "--deep-audit",
            "--outdir",
            str(outdir),
            "--strict",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=env,
        check=False,
    )
    assert audit.returncode == 2
    audit_manifest = json.loads((outdir / "_audit_manifest.json").read_text(encoding="utf-8"))
    assert any("MissingArtifact" in err for err in audit_manifest["errors"])
