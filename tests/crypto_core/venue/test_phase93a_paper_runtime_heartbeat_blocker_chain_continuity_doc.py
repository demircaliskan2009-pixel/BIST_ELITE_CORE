from __future__ import annotations

from pathlib import Path

DOC = Path("docs/crypto_core/PAPER_RUNTIME_HEARTBEAT_BLOCKER_CHAIN_CONTINUITY_93A.md")


def test_phase93a_doc_exists() -> None:
    assert DOC.exists()


def test_phase93a_doc_has_phase_marker() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "phase: 93" in text


def test_phase93a_doc_records_source_sha256() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "a8f151618e8037b9dcc5b2b647c38365d8e59ec08250fd66f86de5a58e916ba0" in text


def test_phase93a_doc_records_next_blocker() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "INDEPENDENT_HUMAN_CONNECTOR_APPROVAL_PROVENANCE_MISSING" in text


def test_phase93a_doc_records_no_scope_widening() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "No scope widening" in text
