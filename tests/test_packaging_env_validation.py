"""Packaging: Environment validation — simulate missing env -> fail.

Ensures commands that require BIST_CORE_* env vars fail with non-zero exit when unset.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _run_cli(args: list[str], env: dict | None = None) -> subprocess.CompletedProcess:
    e = os.environ.copy()
    e["PYTHONPATH"] = str(_project_root() / "src")
    e.pop("BIST_CORE_SNAPSHOT_DIR", None)
    e.pop("BIST_CORE_REGISTRY_PATH", None)
    if env:
        e.update(env)
    return subprocess.run(
        [sys.executable, "-m", "bist_core.cli", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=e,
        cwd=str(_project_root()),
        timeout=15,
    )


def test_market_data_validate_fails_when_snapshot_dir_unset() -> None:
    """market-data validate requires BIST_CORE_SNAPSHOT_DIR or --snapshot-root; fails when both missing."""
    r = _run_cli(["market-data", "validate", "--day", "2025-01-15"])
    assert r.returncode != 0, "Expected non-zero exit when BIST_CORE_SNAPSHOT_DIR unset"
    assert "snapshot_root" in (r.stderr or r.stdout or "").lower() or "BIST_CORE_SNAPSHOT_DIR" in (
        r.stderr or r.stdout or ""
    )


def test_market_data_validate_succeeds_with_snapshot_root_arg(tmp_path: Path) -> None:
    """market-data validate succeeds when --snapshot-root provided (env not required)."""
    (tmp_path / "2025-01-15").mkdir(parents=True)
    (tmp_path / "2025-01-15" / "snapshot.csv").write_text("symbol,close\nX,10.0\n", encoding="utf-8")
    r = _run_cli(["market-data", "validate", "--day", "2025-01-15", "--snapshot-root", str(tmp_path)])
    assert r.returncode == 0, f"Expected success: {r.stderr or r.stdout}"


def test_market_data_validate_succeeds_with_env(tmp_path: Path) -> None:
    """market-data validate succeeds when BIST_CORE_SNAPSHOT_DIR set."""
    (tmp_path / "2025-01-15").mkdir(parents=True)
    (tmp_path / "2025-01-15" / "snapshot.csv").write_text("symbol,close\nX,10.0\n", encoding="utf-8")
    r = _run_cli(["market-data", "validate", "--day", "2025-01-15"], env={"BIST_CORE_SNAPSHOT_DIR": str(tmp_path)})
    assert r.returncode == 0, f"Expected success: {r.stderr or r.stdout}"
