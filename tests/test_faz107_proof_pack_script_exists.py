"""FAZ107: Proof pack script exists and contains required commands."""
from __future__ import annotations

from pathlib import Path


def test_faz107_proof_pack_script_exists() -> None:
    """tools/proof_pack.ps1 must exist."""
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "tools" / "proof_pack.ps1"
    assert script.is_file(), f"tools/proof_pack.ps1 must exist at {script}"


def test_faz107_proof_pack_contains_required_strings() -> None:
    """proof_pack.ps1 must reference verify_alignment.py, pytest, release_check.py."""
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "tools" / "proof_pack.ps1"
    content = script.read_text(encoding="utf-8")
    assert "verify_alignment.py" in content
    assert "pytest" in content
    assert "release_check.py" in content
