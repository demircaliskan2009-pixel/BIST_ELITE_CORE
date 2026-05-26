from __future__ import annotations

from pathlib import Path

DOC = Path("docs/crypto_core/PAPER_PROMOTION_EXECUTION_POST_AUDIT_60A.md")


def test_phase60a_doc_records_required_sources_and_verdict() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert DOC.exists()
    assert "PAPER_PROMOTION_EXECUTION_POST_AUDIT_READY" in text
    assert "`docs/crypto_core/DERIBIT_PAPER_PROMOTION_EXECUTION_TELEMETRY_AUDIT_59B.json`" in text
    assert "`docs/crypto_core/DERIBIT_APPROVED_PAPER_PROMOTION_EXECUTION_58B.json`" in text
    assert "`post_audit_verdict` | `PASS`" in text
    assert "`promotion_telemetry_audit_verdict` | `PASS`" in text
    assert "`promotion_scope` | `PAPER_ONLY_SIMULATION_ONLY`" in text


def test_phase60a_doc_preserves_report_only_no_live_boundary() -> None:
    text = DOC.read_text(encoding="utf-8")

    for required in (
        "NOT_new_campaign_execution: true",
        "NOT_new_session_execution: true",
        "NOT_new_run_execution: true",
        "NOT_new_ledger_mutation: true",
        "NOT_scheduler: true",
        "NOT_automatic_paper_loop: true",
        "NOT_shadow_live_trading: true",
        "NOT_private_api: true",
        "NOT_credentials: true",
        "NOT_exchange_orders: true",
        "NOT_execution_adapter: true",
        "PAPER_PROMOTED_RUNTIME_READINESS_NOT_READY",
    ):
        assert required in text
