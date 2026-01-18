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
        "symbol,close\nAKAAA,\nAKBBB,\nAAA,\nBBB,\nCCC,\n",
        encoding="utf-8",
    )
    return snapshot_root


def _run_build(env: dict, outdir: Path, extra_args: list[str]) -> subprocess.CompletedProcess:
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
            *extra_args,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=env,
        check=False,
    )


def test_cli_dossier_manifest_and_strict(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")

    snapshot_root = _write_snapshot(tmp_path)
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snapshot_root)

    outdir = tmp_path / "out_manifest"
    result = _run_build(env, outdir, [])
    assert result.returncode == 0

    manifest_path = outdir / "_manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    required_keys = {
        "schema_version",
        "day",
        "outdir",
        "total",
        "ok",
        "errors",
        "error_list",
        "runtime_ms",
        "provenance",
    }
    assert required_keys.issubset(manifest.keys())

    outdir_strict = tmp_path / "out_strict"
    result_strict = _run_build(env, outdir_strict, ["--symbols", "ZZZ", "--strict"])
    assert result_strict.returncode == 2
    strict_manifest = json.loads((outdir_strict / "_manifest.json").read_text(encoding="utf-8"))
    assert strict_manifest["errors"] > 0
    assert any(item.get("symbol") == "ZZZ" for item in strict_manifest["error_list"])
