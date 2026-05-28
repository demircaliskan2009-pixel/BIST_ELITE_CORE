from __future__ import annotations

from pathlib import Path

DOC = Path("docs/crypto_core/APPROVED_PAPER_RUNTIME_HEARTBEAT_EXECUTION_74A.md")


def test_phase74a_doc_declares_execution_scope_and_boundary() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert DOC.exists()
    assert "status: APPROVED_PAPER_RUNTIME_HEARTBEAT_EXECUTION_EXECUTED" in text
    assert "scope: REPORT_ONLY_APPROVED_PAPER_RUNTIME_HEARTBEAT_EXECUTION" in text
    assert "NOT_runtime_loop: true" in text
    assert "NOT_runtime_order_routing: true" in text
    assert "NOT_live_shadow_trading: true" in text
    assert "NOT_campaign_session_run_execution: true" in text
    assert "NOT_ledger_mutation: true" in text


def test_phase74a_doc_declares_approved_execution_metadata() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert "`heartbeat_execution_status` | `EXECUTED`" in text
    assert "`execution_mode` | `APPROVED_PAPER_RUNTIME_HEARTBEAT_ONLY`" in text
    assert "`approval_status` | `APPROVED`" in text
    assert "`operator_id` | `demir_operator`" in text
    assert "`approval_decision` | `APPROVE_PAPER_RUNTIME_HEARTBEAT_REVIEW`" in text
    assert "`approval_scope` | `PAPER_ONLY_SIMULATION_ONLY`" in text


def test_phase74a_doc_points_to_next_blocker() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "PAPER_RUNTIME_HEARTBEAT_EXECUTION_TELEMETRY_NOT_READY" in text
