from __future__ import annotations

from pathlib import Path

DOC = Path("docs/crypto_core/PAPER_RUNTIME_OPERATOR_TRIGGERED_HEARTBEAT_70A.md")


def test_phase70a_doc_declares_heartbeat_scope_and_boundary() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert DOC.exists()
    assert "status: PAPER_RUNTIME_OPERATOR_TRIGGERED_HEARTBEAT_READY" in text
    assert "scope: REPORT_ONLY_PAPER_RUNTIME_OPERATOR_TRIGGERED_HEARTBEAT" in text
    assert "NOT_runtime_loop: true" in text
    assert "NOT_runtime_order_routing: true" in text
    assert "NOT_live_shadow_trading: true" in text
    assert "NOT_campaign_session_run_execution: true" in text
    assert "NOT_ledger_mutation: true" in text


def test_phase70a_doc_points_to_phase70_next_blocker() -> None:
    text = DOC.read_text(encoding="utf-8")
    normalized = " ".join(text.split())

    assert "PAPER_RUNTIME_HEARTBEAT_TELEMETRY_NOT_READY" in text
    assert "no-live and no-order-routing boundary" in normalized
