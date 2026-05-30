from __future__ import annotations

from pathlib import Path

DOC = Path("docs/crypto_core/PAPER_RUNTIME_HEARTBEAT_OPERATOR_APPROVAL_EXECUTION_73A.md")


def test_phase73a_doc_declares_approval_scope_and_boundary() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert DOC.exists()
    assert "status: PAPER_RUNTIME_HEARTBEAT_OPERATOR_APPROVAL_EXECUTED" in text
    assert "scope: REPORT_ONLY_PAPER_RUNTIME_HEARTBEAT_OPERATOR_APPROVAL" in text
    assert "NOT_runtime_loop: true" in text
    assert "NOT_runtime_order_routing: true" in text
    assert "NOT_live_shadow_trading: true" in text
    assert "NOT_campaign_session_run_execution: true" in text
    assert "NOT_ledger_mutation: true" in text


def test_phase73a_doc_declares_operator_approval_metadata() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert "`approval_status` | `APPROVED`" in text
    assert "`operator_metadata_required` | `false`" in text
    assert "`operator_id` | `demir_operator`" in text
    assert "`reviewed_at_iso` | `2026-05-28T20:04:43Z`" in text
    assert "`approval_decision` | `APPROVE_PAPER_RUNTIME_HEARTBEAT_REVIEW`" in text
    assert "`approval_scope` | `PAPER_ONLY_SIMULATION_ONLY`" in text


def test_phase73a_doc_points_to_next_blocker() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "APPROVED_PAPER_RUNTIME_HEARTBEAT_EXECUTION_NOT_READY" in text
