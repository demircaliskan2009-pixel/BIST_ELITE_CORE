from __future__ import annotations

from pathlib import Path

DOC = Path("docs/crypto_core/PAPER_RUNTIME_HEARTBEAT_BLOCKER_CHAIN_CONTINUITY_101A.md")


def test_phase101a_doc_exists() -> None:
    assert DOC.exists()


def test_phase101a_doc_has_phase_marker() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "phase: 101" in text


def test_phase101a_doc_records_source_sha256() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "4e6825f11f8d778b665e6a8beb1258dcf84e16efb958439cf2bc35b9c5b5d062" in text


def test_phase101a_doc_records_next_blocker() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "INDEPENDENT_HUMAN_CONNECTOR_APPROVAL_PROVENANCE_MISSING" in text


def test_phase101a_doc_records_no_scope_widening() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "No scope widening" in text
