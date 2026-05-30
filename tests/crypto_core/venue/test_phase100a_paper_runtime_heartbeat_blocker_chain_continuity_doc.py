from __future__ import annotations

from pathlib import Path

DOC = Path("docs/crypto_core/PAPER_RUNTIME_HEARTBEAT_BLOCKER_CHAIN_CONTINUITY_100A.md")


def test_phase100a_doc_exists() -> None:
    assert DOC.exists()


def test_phase100a_doc_has_phase_marker() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "phase: 100" in text


def test_phase100a_doc_records_source_sha256() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "26227080d0196922b3f54655a404b8d1525e14a9dfce513200dd3c112d22d020" in text


def test_phase100a_doc_records_next_blocker() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "INDEPENDENT_HUMAN_CONNECTOR_APPROVAL_PROVENANCE_MISSING" in text


def test_phase100a_doc_records_no_scope_widening() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "No scope widening" in text
