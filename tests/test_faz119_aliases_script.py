"""FAZ119: PowerShell aliases script exists and contains required strings."""
from __future__ import annotations

from pathlib import Path


def test_faz119_aliases_script_exists() -> None:
    """tools/aliases.ps1 must exist."""
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "tools" / "aliases.ps1"
    assert script.is_file(), f"tools/aliases.ps1 must exist at {script}"


def test_faz119_aliases_contains_required_strings() -> None:
    """aliases.ps1 must define clean_repo, proof_pack, run_proof."""
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "tools" / "aliases.ps1"
    content = script.read_text(encoding="utf-8")
    assert "clean_repo" in content
    assert "proof_pack" in content
    assert "run_proof" in content
