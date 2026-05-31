from __future__ import annotations

from pathlib import Path

DOC = Path("docs/crypto_core/PAPER_RUNTIME_HEARTBEAT_BLOCKER_CHAIN_CONTINUITY_107A.md")


def test_phase107a_doc_exists() -> None:
    assert DOC.exists()


def test_phase107a_doc_has_phase_marker() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "phase: 107" in text


def test_phase107a_doc_records_source_sha256() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "366d62d6bb4941c390c50cd2f0a0e34a6b238f2c6149efbf111b08825421d6bb" in text


def test_phase107a_doc_records_next_blocker() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "INDEPENDENT_HUMAN_CONNECTOR_APPROVAL_PROVENANCE_MISSING" in text


def test_phase107a_doc_records_no_scope_widening() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "No scope widening" in text
