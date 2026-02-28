"""FAZ120: Windows prod runbook and release checklist docs exist and contain key strings."""

from __future__ import annotations

from pathlib import Path


def _docs_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "docs"


def test_faz120_windows_prod_runbook_exists() -> None:
    """docs/WINDOWS_PROD_RUNBOOK.md must exist."""
    path = _docs_dir() / "WINDOWS_PROD_RUNBOOK.md"
    assert path.is_file(), f"docs/WINDOWS_PROD_RUNBOOK.md must exist at {path}"


def test_faz120_release_checklist_exists() -> None:
    """docs/RELEASE_CHECKLIST.md must exist."""
    path = _docs_dir() / "RELEASE_CHECKLIST.md"
    assert path.is_file(), f"docs/RELEASE_CHECKLIST.md must exist at {path}"


def test_faz120_runbook_contains_key_strings() -> None:
    """WINDOWS_PROD_RUNBOOK.md must include OPENAI_API_KEY, setx, $env:, BIST_CORE_ALLOW_NETWORK, doctor."""
    path = _docs_dir() / "WINDOWS_PROD_RUNBOOK.md"
    content = path.read_text(encoding="utf-8")
    assert "OPENAI_API_KEY" in content
    assert "setx" in content
    assert "$env:" in content
    assert "BIST_CORE_ALLOW_NETWORK" in content
    assert "python -m bist_core.cli.main doctor" in content
