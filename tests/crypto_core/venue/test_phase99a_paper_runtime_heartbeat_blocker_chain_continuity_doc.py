from __future__ import annotations

from pathlib import Path

DOC = Path("docs/crypto_core/PAPER_RUNTIME_HEARTBEAT_BLOCKER_CHAIN_CONTINUITY_99A.md")


def test_phase99a_doc_exists() -> None:
    assert DOC.exists()


def test_phase99a_doc_has_phase_marker() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "phase: 99" in text


def test_phase99a_doc_records_source_sha256() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "6ec69c40e5f1052689ca1785877efc49af04e64875f20d1bdeb09fdd9ef16828" in text


def test_phase99a_doc_records_next_blocker() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "INDEPENDENT_HUMAN_CONNECTOR_APPROVAL_PROVENANCE_MISSING" in text


def test_phase99a_doc_records_no_scope_widening() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "No scope widening" in text
