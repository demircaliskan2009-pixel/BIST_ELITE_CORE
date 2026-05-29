from __future__ import annotations

from pathlib import Path

DOC = Path("docs/crypto_core/PAPER_RUNTIME_HEARTBEAT_BLOCKER_CHAIN_CONTINUITY_90A.md")


def test_phase90a_doc_exists() -> None:
    assert DOC.exists()


def test_phase90a_doc_has_phase_marker() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "phase: 90" in text


def test_phase90a_doc_records_source_sha256() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "9860b111ffd62eee7e6b41efbc14e2e676b62668b0cc557576b22d6ded20ac29" in text


def test_phase90a_doc_records_next_blocker() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "INDEPENDENT_HUMAN_CONNECTOR_APPROVAL_PROVENANCE_MISSING" in text


def test_phase90a_doc_records_no_scope_widening() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "No scope widening" in text
