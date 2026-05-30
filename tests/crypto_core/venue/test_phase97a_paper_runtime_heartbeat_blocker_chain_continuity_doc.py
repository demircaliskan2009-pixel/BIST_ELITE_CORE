from __future__ import annotations

from pathlib import Path

DOC = Path("docs/crypto_core/PAPER_RUNTIME_HEARTBEAT_BLOCKER_CHAIN_CONTINUITY_97A.md")


def test_phase97a_doc_exists() -> None:
    assert DOC.exists()


def test_phase97a_doc_has_phase_marker() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "phase: 97" in text


def test_phase97a_doc_records_source_sha256() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "e084b32c0d1e858a8807ca5ea8e945f07ac411139248bbe1ae4b9fa960337aff" in text


def test_phase97a_doc_records_next_blocker() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "INDEPENDENT_HUMAN_CONNECTOR_APPROVAL_PROVENANCE_MISSING" in text


def test_phase97a_doc_records_no_scope_widening() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "No scope widening" in text
