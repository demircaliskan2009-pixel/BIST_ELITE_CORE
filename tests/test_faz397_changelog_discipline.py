"""FAZ397: Changelog discipline — CHANGELOG.md exists; format [fazNNN]; entry per phase."""
from __future__ import annotations

import re
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_faz397_changelog_exists() -> None:
    """CHANGELOG.md must exist at repo root."""
    changelog = _repo_root() / "CHANGELOG.md"
    assert changelog.is_file(), "CHANGELOG.md must exist at repo root"


def test_faz397_changelog_format_valid() -> None:
    """Changelog entries must match [fazNNN] format."""
    changelog = _repo_root() / "CHANGELOG.md"
    text = changelog.read_text(encoding="utf-8")
    entries = re.findall(r"\[faz(\d+)\]", text)
    assert len(entries) >= 1, "CHANGELOG.md must have at least one [fazNNN] entry"
    for n in entries:
        assert n.isdigit() and len(n) >= 1, f"faz{n} must be numeric phase id"


def test_faz397_changelog_has_phase_entries() -> None:
    """Changelog must have entries for key phases from ledger."""
    changelog = _repo_root() / "CHANGELOG.md"
    text = changelog.read_text(encoding="utf-8")
    key_phases = ["faz126", "faz140", "faz393"]
    for phase in key_phases:
        assert f"[{phase}]" in text, f"CHANGELOG.md must mention [{phase}]"
