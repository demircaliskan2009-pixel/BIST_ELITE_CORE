"""FAZ108: Clean repo script exists and contains required logic."""
from __future__ import annotations

from pathlib import Path


def test_faz108_clean_repo_script_exists() -> None:
    """tools/clean_repo.ps1 must exist."""
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "tools" / "clean_repo.ps1"
    assert script.is_file(), f"tools/clean_repo.ps1 must exist at {script}"


def test_faz108_clean_repo_contains_required_strings() -> None:
    """clean_repo.ps1 must reference __pycache__, Remove-Item, proof_."""
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "tools" / "clean_repo.ps1"
    content = script.read_text(encoding="utf-8")
    assert "__pycache__" in content
    assert "Remove-Item" in content
    assert "proof_" in content
