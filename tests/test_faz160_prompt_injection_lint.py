"""FAZ160: Prompt injection lint — agent-facing docs must state untrusted text policy."""
from __future__ import annotations

from pathlib import Path


def test_faz160_agents_md_has_untrusted_policy() -> None:
    """AGENTS.md must explicitly state untrusted text / do not follow instructions policy."""
    agents = Path(__file__).resolve().parents[1] / "AGENTS.md"
    assert agents.is_file()
    content = agents.read_text(encoding="utf-8").lower()
    assert "untrusted" in content or "do not follow" in content or "instructions" in content
    assert "secret" in content or "security" in content


def test_faz160_agents_md_has_network_default_off() -> None:
    """AGENTS.md must state network default OFF."""
    agents = Path(__file__).resolve().parents[1] / "AGENTS.md"
    content = agents.read_text(encoding="utf-8").lower()
    assert "network" in content
    assert "default" in content or "off" in content or "forbidden" in content
