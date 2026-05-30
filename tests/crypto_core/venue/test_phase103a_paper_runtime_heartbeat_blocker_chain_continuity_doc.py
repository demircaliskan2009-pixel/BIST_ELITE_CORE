from __future__ import annotations

from pathlib import Path

DOC = Path("docs/crypto_core/PAPER_RUNTIME_HEARTBEAT_BLOCKER_CHAIN_CONTINUITY_103A.md")


def test_phase103a_doc_exists() -> None:
    assert DOC.exists()


def test_phase103a_doc_has_phase_marker() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "phase: 103" in text


def test_phase103a_doc_records_source_sha256() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "f03de8f992dc33104870f4b18615fcfc5fa1aaf254c52a96e9f398e9b84867d2" in text


def test_phase103a_doc_records_next_blocker() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "INDEPENDENT_HUMAN_CONNECTOR_APPROVAL_PROVENANCE_MISSING" in text


def test_phase103a_doc_records_no_scope_widening() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "No scope widening" in text
