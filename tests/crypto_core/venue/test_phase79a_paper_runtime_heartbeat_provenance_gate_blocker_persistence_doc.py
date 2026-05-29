from __future__ import annotations

from pathlib import Path

DOC = Path("docs/crypto_core/PAPER_RUNTIME_HEARTBEAT_PROVENANCE_GATE_BLOCKER_PERSISTENCE_79A.md")


def test_phase79a_doc_declares_status_and_scope() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "status: PAPER_RUNTIME_HEARTBEAT_PROVENANCE_GATE_BLOCKER_PERSISTENCE_COMPLETE" in text
    assert "scope: REPORT_ONLY_PAPER_RUNTIME_HEARTBEAT_PROVENANCE_GATE_BLOCKER_PERSISTENCE" in text


def test_phase79a_doc_declares_boundaries() -> None:
    text = DOC.read_text(encoding="utf-8")
    for token in (
        "- NOT_runtime_loop: true",
        "- NOT_runtime_order_routing: true",
        "- NOT_live_shadow_trading: true",
        "- NOT_campaign_session_run_execution: true",
        "- NOT_ledger_mutation: true",
    ):
        assert token in text


def test_phase79a_doc_declares_next_blocker() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "INDEPENDENT_HUMAN_CONNECTOR_APPROVAL_PROVENANCE_MISSING" in text
