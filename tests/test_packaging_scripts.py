"""Packaging: Scripts exist and proof_pack is runnable."""

from __future__ import annotations

import subprocess
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_install_ps1_exists() -> None:
    """install.ps1 exists at repo root."""
    assert (_project_root() / "install.ps1").is_file()


def test_run_ps1_exists() -> None:
    """run.ps1 exists at repo root."""
    assert (_project_root() / "run.ps1").is_file()


def test_proof_pack_ps1_exists() -> None:
    """proof_pack.ps1 exists at repo root (wrapper) and tools/."""
    root = _project_root()
    assert (root / "proof_pack.ps1").is_file()
    assert (root / "tools" / "proof_pack.ps1").is_file()


def test_run_ps1_help_succeeds() -> None:
    """run.ps1 with no args shows help (exit 0)."""
    root = _project_root()
    r = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(root / "run.ps1")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(root),
        env={**__import__("os").environ, "PYTHONPATH": str(root / "src")},
        timeout=15,
    )
    assert r.returncode == 0, f"run.ps1 failed: {r.stderr or r.stdout}"
    assert "usage" in (r.stdout or "").lower() or "bist" in (r.stdout or "").lower()


def test_bist_core_cli_importable() -> None:
    """bist_core.cli is importable (no unmet dependencies)."""
    import bist_core.cli  # noqa: F401
    from bist_core.cli.main import main

    assert callable(main)
