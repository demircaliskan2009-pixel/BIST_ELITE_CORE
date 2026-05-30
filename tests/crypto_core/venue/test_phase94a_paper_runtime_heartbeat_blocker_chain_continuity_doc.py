from __future__ import annotations

from pathlib import Path

DOC = Path("docs/crypto_core/PAPER_RUNTIME_HEARTBEAT_BLOCKER_CHAIN_CONTINUITY_94A.md")


def test_phase94a_doc_exists() -> None:
    assert DOC.exists()


def test_phase94a_doc_has_phase_marker() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "phase: 94" in text


def test_phase94a_doc_records_source_sha256() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "1352eb329d00a7dcb74bb798fd2aeff688bbae63d94fbc6957cd707e6938d69e" in text


def test_phase94a_doc_records_next_blocker() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "INDEPENDENT_HUMAN_CONNECTOR_APPROVAL_PROVENANCE_MISSING" in text


def test_phase94a_doc_records_no_scope_widening() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "No scope widening" in text
