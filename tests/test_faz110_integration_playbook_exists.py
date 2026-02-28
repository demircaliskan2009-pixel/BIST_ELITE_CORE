"""FAZ110: Integration playbook doc exists and contains key integration strings."""

from __future__ import annotations

from pathlib import Path


def test_faz110_integration_playbook_exists() -> None:
    """docs/INTEGRATION_PLAYBOOK.md must exist."""
    repo_root = Path(__file__).resolve().parents[1]
    path = repo_root / "docs" / "INTEGRATION_PLAYBOOK.md"
    assert path.is_file(), f"docs/INTEGRATION_PLAYBOOK.md must exist at {path}"


def test_faz110_integration_playbook_contains_key_strings() -> None:
    """Playbook must mention BIST_CORE_ALLOW_NETWORK, BrokerAdapter, VendorAPIProvider, KapHtmlEventsProvider, python -m bist_core.cli."""
    repo_root = Path(__file__).resolve().parents[1]
    path = repo_root / "docs" / "INTEGRATION_PLAYBOOK.md"
    content = path.read_text(encoding="utf-8")
    required = [
        "BIST_CORE_ALLOW_NETWORK",
        "BrokerAdapter",
        "VendorAPIProvider",
        "KapHtmlEventsProvider",
        "python -m bist_core.cli",
    ]
    for s in required:
        assert s in content, f"INTEGRATION_PLAYBOOK.md must contain {s!r}"
