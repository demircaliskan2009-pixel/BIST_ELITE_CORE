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
        "symbol,close\nAAA,\nBBB,\nCCC,\n",
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


def _load_manifest(outdir: Path) -> dict:
    return json.loads((outdir / "_manifest.json").read_text(encoding="utf-8"))


def _load_symbol_payloads(outdir: Path) -> dict[str, dict]:
    payloads = {}
    for path in outdir.glob("*.json"):
        if path.name == "_manifest.json":
            continue
        payloads[path.name] = json.loads(path.read_text(encoding="utf-8"))
    return payloads


def test_cli_dossier_idempotent(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")

    snapshot_root = _write_snapshot(tmp_path)
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snapshot_root)

    outdir = tmp_path / "out"
    result_first = _run_build(env, outdir)
    assert result_first.returncode == 0
    manifest_first = _load_manifest(outdir)
    payloads_first = _load_symbol_payloads(outdir)

    result_second = _run_build(env, outdir)
    assert result_second.returncode == 0
    manifest_second = _load_manifest(outdir)
    payloads_second = _load_symbol_payloads(outdir)

    assert manifest_first == manifest_second
    assert payloads_first == payloads_second
