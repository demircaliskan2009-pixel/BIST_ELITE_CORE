from __future__ import annotations

from pathlib import Path

DOC = Path("docs/crypto_core/PAPER_RUNTIME_HEARTBEAT_BLOCKER_CHAIN_CONTINUITY_104A.md")


def test_phase104a_doc_exists() -> None:
    assert DOC.exists()


def test_phase104a_doc_has_phase_marker() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "phase: 104" in text


def test_phase104a_doc_records_source_sha256() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "61bbe5b28d3ebdcc780a754f14fbfd6b488cf988b0a89274fbfa85727bd34d2c" in text


def test_phase104a_doc_records_next_blocker() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "INDEPENDENT_HUMAN_CONNECTOR_APPROVAL_PROVENANCE_MISSING" in text


def test_phase104a_doc_records_no_scope_widening() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "No scope widening" in text
