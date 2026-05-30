from __future__ import annotations

from pathlib import Path

DOC = Path("docs/crypto_core/PAPER_RUNTIME_HEARTBEAT_OPERATOR_REVIEW_PROPOSAL_72A.md")


def test_phase72a_doc_declares_proposal_scope_and_boundary() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert DOC.exists()
    assert "status: PAPER_RUNTIME_HEARTBEAT_OPERATOR_REVIEW_PROPOSAL_READY" in text
    assert "scope: REPORT_ONLY_PAPER_RUNTIME_HEARTBEAT_OPERATOR_REVIEW_PROPOSAL" in text
    assert "NOT_new_runtime_heartbeat: true" in text
    assert "NOT_heartbeat_loop: true" in text
    assert "NOT_runtime_loop: true" in text
    assert "NOT_runtime_order_routing: true" in text
    assert "NOT_live_shadow_trading: true" in text
    assert "NOT_campaign_session_run_execution: true" in text
    assert "NOT_ledger_mutation: true" in text


def test_phase72a_doc_declares_operator_metadata_contract() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert "`proposal_status` | `READY_FOR_OPERATOR_REVIEW`" in text
    assert "`approval_status` | `NOT_APPROVED`" in text
    assert "`operator_metadata_required` | `true`" in text
    assert "`operator_id` | `null`" in text
    assert "`reviewed_at_iso` | `null`" in text
    assert "`approval_decision` | `null`" in text


def test_phase72a_doc_points_to_phase72_next_blocker() -> None:
    text = DOC.read_text(encoding="utf-8")
    normalized = " ".join(text.split())

    assert "PAPER_RUNTIME_HEARTBEAT_OPERATOR_APPROVAL_NOT_READY" in text
    assert "requires explicit operator approval evidence" in normalized
