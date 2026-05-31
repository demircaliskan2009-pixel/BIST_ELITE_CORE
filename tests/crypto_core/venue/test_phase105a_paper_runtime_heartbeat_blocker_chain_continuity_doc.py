from __future__ import annotations

from pathlib import Path

DOC = Path("docs/crypto_core/PAPER_RUNTIME_HEARTBEAT_BLOCKER_CHAIN_CONTINUITY_105A.md")


def test_phase105a_doc_exists() -> None:
    assert DOC.exists()


def test_phase105a_doc_has_phase_marker() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "phase: 105" in text


def test_phase105a_doc_records_source_sha256() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "1a66a27e866bd256d8e801fe3e927beea3429a214399804cba4c6c6a7c07c341" in text


def test_phase105a_doc_records_next_blocker() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "INDEPENDENT_HUMAN_CONNECTOR_APPROVAL_PROVENANCE_MISSING" in text


def test_phase105a_doc_records_no_scope_widening() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "No scope widening" in text
