from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _write_snapshot(tmp_path: Path) -> Path:
    snapshot_root = tmp_path / "data" / "eod" / "snapshots"
    day_dir = snapshot_root / "2099-01-01"
    day_dir.mkdir(parents=True)
    (day_dir / "snapshot.csv").write_text(
        "symbol,close\nAAA,\n",
        encoding="utf-8",
    )
    return snapshot_root


def _run_build(env: dict, outdir: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
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


def test_manifest_provenance(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")

    snapshot_root = _write_snapshot(tmp_path)
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snapshot_root)

    outdir = tmp_path / "out"
    result = _run_build(env, outdir)
    assert result.returncode == 0

    manifest = json.loads((outdir / "_manifest.json").read_text(encoding="utf-8"))
    provenance = manifest.get("provenance")
    assert isinstance(provenance, dict)
    assert "python" in provenance
    assert "platform" in provenance
    assert "cli_args" in provenance
    assert "git_sha" in provenance

    assert isinstance(provenance["python"], str)
    assert isinstance(provenance["platform"], str)
    assert isinstance(provenance["cli_args"], dict)

    cli_args = provenance["cli_args"]
    assert "day" in cli_args
    assert "outdir" in cli_args
