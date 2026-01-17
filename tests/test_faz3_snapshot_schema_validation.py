from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _run_cli(env: dict, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "bist_core.cli", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )


def test_snapshot_schema_validation(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")
    env["BIST_CORE_REGISTRY_PATH"] = str(tmp_path / "registry.json")
    env["BIST_CORE_SNAPSHOT_DIR"] = str(tmp_path / "snapshots")

    bad_dir = tmp_path / "bad"
    bad_dir.mkdir()
    (bad_dir / "bad.csv").write_text(
        "symbol,date,price\nAAA,2025-01-01,10.0\n",
        encoding="utf-8",
    )
    ok_dir = tmp_path / "ok"
    ok_dir.mkdir()
    (ok_dir / "ok.csv").write_text(
        "symbol,date,close\nAAA,2025-01-01,10.0\n",
        encoding="utf-8",
    )

    result = _run_cli(
        env,
        "data",
        "register",
        "--id",
        "bad_ds",
        "--path",
        str(bad_dir),
        "--format",
        "csv",
    )
    assert result.returncode == 0

    result = _run_cli(
        env,
        "data",
        "snapshot",
        "--id",
        "bad_ds",
        "--day",
        "2025-01-01",
    )
    assert result.returncode != 0
    assert "Snapshot schema invalid" in (result.stdout + result.stderr)

    result = _run_cli(
        env,
        "data",
        "register",
        "--id",
        "ok_ds",
        "--path",
        str(ok_dir),
        "--format",
        "csv",
    )
    assert result.returncode == 0

    result = _run_cli(
        env,
        "data",
        "snapshot",
        "--id",
        "ok_ds",
        "--day",
        "2025-01-01",
    )
    assert result.returncode == 0
