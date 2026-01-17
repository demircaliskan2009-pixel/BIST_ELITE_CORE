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

    legacy_dir = tmp_path / "legacy"
    legacy_dir.mkdir()
    (legacy_dir / "legacy.csv").write_text(
        "symbol,close\nAAA,10.0\n",
        encoding="utf-8",
    )
    new_dir = tmp_path / "new"
    new_dir.mkdir()
    (new_dir / "new.csv").write_text(
        "symbol,close,date\nAAA,10.0,2025-01-01\n",
        encoding="utf-8",
    )
    bad_dir = tmp_path / "bad"
    bad_dir.mkdir()
    (bad_dir / "bad.csv").write_text(
        "ticker,last\nAAA,10.0\n",
        encoding="utf-8",
    )

    result = _run_cli(
        env,
        "data",
        "register",
        "--id",
        "legacy_ds",
        "--path",
        str(legacy_dir),
        "--format",
        "csv",
    )
    assert result.returncode == 0

    result = _run_cli(
        env,
        "data",
        "snapshot",
        "--id",
        "legacy_ds",
        "--day",
        "2025-01-01",
    )
    assert result.returncode == 0

    result = _run_cli(
        env,
        "data",
        "register",
        "--id",
        "new_ds",
        "--path",
        str(new_dir),
        "--format",
        "csv",
    )
    assert result.returncode == 0

    result = _run_cli(
        env,
        "data",
        "snapshot",
        "--id",
        "new_ds",
        "--day",
        "2025-01-01",
    )
    assert result.returncode == 0

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
