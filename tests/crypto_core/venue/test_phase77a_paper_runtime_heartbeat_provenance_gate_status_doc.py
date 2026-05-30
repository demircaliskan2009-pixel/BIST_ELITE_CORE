from __future__ import annotations

from pathlib import Path

DOC = Path("docs/crypto_core/PAPER_RUNTIME_HEARTBEAT_PROVENANCE_GATE_STATUS_77A.md")


def test_phase77a_doc_declares_provenance_gate_scope_and_boundary() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert DOC.exists()
    assert "status: PAPER_RUNTIME_HEARTBEAT_PROVENANCE_GATE_STATUS_COMPLETE" in text
    assert "scope: REPORT_ONLY_PAPER_RUNTIME_HEARTBEAT_PROVENANCE_GATE_STATUS" in text
    assert "NOT_runtime_loop: true" in text
    assert "NOT_runtime_order_routing: true" in text
    assert "NOT_live_shadow_trading: true" in text
    assert "NOT_campaign_session_run_execution: true" in text
    assert "NOT_ledger_mutation: true" in text


def test_phase77a_doc_declares_provenance_gate_metadata() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert "`heartbeat_execution_post_audit_status` | `PASS`" in text
    assert "`b5_status` | `BLOCKED`" in text
    assert "`connector_enablement_ready` | `False`" in text
    assert "`provenance_reason` | `INDEPENDENT_HUMAN_CONNECTOR_APPROVAL_PROVENANCE_MISSING`" in text
    assert "`connector_ready_dialects_count` | `1`" in text


def test_phase77a_doc_points_to_next_blocker() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert "INDEPENDENT_HUMAN_CONNECTOR_APPROVAL_PROVENANCE_MISSING" in text
