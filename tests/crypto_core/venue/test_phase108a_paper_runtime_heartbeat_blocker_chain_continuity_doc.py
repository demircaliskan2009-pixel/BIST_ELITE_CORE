from __future__ import annotations

from pathlib import Path

DOC = Path("docs/crypto_core/PAPER_RUNTIME_HEARTBEAT_BLOCKER_CHAIN_CONTINUITY_108A.md")


def test_phase108a_doc_exists() -> None:
    assert DOC.exists()


def test_phase108a_doc_has_phase_marker() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "phase: 108" in text


def test_phase108a_doc_records_source_sha256() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "f5b6831092b01de811bcd4e7e36c7d00e48752a4f3a0eba86ac8ca468798f03f" in text


def test_phase108a_doc_records_next_blocker() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "INDEPENDENT_HUMAN_CONNECTOR_APPROVAL_PROVENANCE_MISSING" in text


def test_phase108a_doc_records_no_scope_widening() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "No scope widening" in text
