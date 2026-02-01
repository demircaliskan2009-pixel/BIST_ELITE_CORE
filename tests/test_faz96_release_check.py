"""FAZ96: Release check — minimal test: script exists, alignment-only and schema-only pass from repo."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_faz96_release_check_script_exists() -> None:
    """tools/release_check.py exists and is runnable."""
    root = _repo_root()
    script = root / "tools" / "release_check.py"
    assert script.is_file(), "tools/release_check.py must exist"


def test_faz96_release_check_alignment_only_exit_0() -> None:
    """release_check.py --alignment-only exits 0 when repo alignment doc is complete."""
    root = _repo_root()
    script = root / "tools" / "release_check.py"
    proc = subprocess.run(
        [sys.executable, str(script), "--alignment-only"],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, (proc.stdout, proc.stderr)


def test_faz96_release_check_schema_only_exit_0() -> None:
    """release_check.py --schema-only exits 0 when config/strategy.json and config/core.json exist and are valid."""
    root = _repo_root()
    script = root / "tools" / "release_check.py"
    proc = subprocess.run(
        [sys.executable, str(script), "--schema-only"],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert proc.returncode == 0, (proc.stdout, proc.stderr)


def test_faz96_release_check_help() -> None:
    """release_check.py --help exits 0."""
    root = _repo_root()
    script = root / "tools" / "release_check.py"
    proc = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert proc.returncode == 0
    assert "alignment" in proc.stdout or "tests" in proc.stdout
