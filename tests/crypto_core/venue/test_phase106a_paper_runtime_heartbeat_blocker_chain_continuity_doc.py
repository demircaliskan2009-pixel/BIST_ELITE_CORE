from __future__ import annotations

from pathlib import Path

DOC = Path("docs/crypto_core/PAPER_RUNTIME_HEARTBEAT_BLOCKER_CHAIN_CONTINUITY_106A.md")


def test_phase106a_doc_exists() -> None:
    assert DOC.exists()


def test_phase106a_doc_has_phase_marker() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "phase: 106" in text


def test_phase106a_doc_records_source_sha256() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "9abfb7cf84c4a789ef10029102d0e6ea9427196e2e5207b486ccf2a0de20ead6" in text


def test_phase106a_doc_records_next_blocker() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "INDEPENDENT_HUMAN_CONNECTOR_APPROVAL_PROVENANCE_MISSING" in text


def test_phase106a_doc_records_no_scope_widening() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "No scope widening" in text
