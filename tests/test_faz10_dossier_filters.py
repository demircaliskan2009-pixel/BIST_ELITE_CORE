from __future__ import annotations

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


def _list_symbol_files(outdir: Path) -> list[str]:
    return sorted([p.name for p in outdir.glob("*.json") if p.name != "_manifest.json"])


def test_cli_dossier_filters(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")

    snapshot_root = _write_snapshot(tmp_path)
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snapshot_root)

    outdir_regex = tmp_path / "out_regex"
    result_regex = _run_build(env, outdir_regex, ["--regex", "^AK"])
    assert result_regex.returncode == 0
    assert _list_symbol_files(outdir_regex) == ["AKAAA.json", "AKBBB.json"]

    outdir_limit = tmp_path / "out_limit"
    result_limit = _run_build(env, outdir_limit, ["--limit", "2"])
    assert result_limit.returncode == 0
    assert _list_symbol_files(outdir_limit) == ["AKAAA.json", "AKBBB.json"]

    outdir_symbols = tmp_path / "out_symbols"
    result_symbols = _run_build(env, outdir_symbols, ["--symbols", "AAA,CCC"])
    assert result_symbols.returncode == 0
    assert _list_symbol_files(outdir_symbols) == ["AAA.json", "CCC.json"]
