from __future__ import annotations

from pathlib import Path

DOC = Path("docs/crypto_core/PAPER_RUNTIME_HEARTBEAT_BLOCKER_CHAIN_CONTINUITY_95A.md")


def test_phase95a_doc_exists() -> None:
    assert DOC.exists()


def test_phase95a_doc_has_phase_marker() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "phase: 95" in text


def test_phase95a_doc_records_source_sha256() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "8cc57ca7995c3b320ef0580f08f67f155397d38fbd98291dc966a6c859c888d1" in text


def test_phase95a_doc_records_next_blocker() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "INDEPENDENT_HUMAN_CONNECTOR_APPROVAL_PROVENANCE_MISSING" in text


def test_phase95a_doc_records_no_scope_widening() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "No scope widening" in text
