from __future__ import annotations

from pathlib import Path

DOC = Path("docs/crypto_core/PAPER_PROMOTED_RUNTIME_READINESS_61A.md")


def test_phase61a_doc_records_required_source_and_verdict() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert DOC.exists()
    assert "PAPER_PROMOTED_RUNTIME_READINESS_READY" in text
    assert "`docs/crypto_core/DERIBIT_PAPER_PROMOTION_EXECUTION_POST_AUDIT_60B.json`" in text
    assert "`runtime_readiness_verdict` | `PASS`" in text
    assert "`ready_for_paper_runtime` | `True`" in text
    assert "`runtime_enabled` | `False`" in text


def test_phase61a_doc_preserves_no_runtime_no_live_boundary() -> None:
    text = DOC.read_text(encoding="utf-8")

    for required in (
        "NOT_runtime_start: true",
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
        "PAPER_PROMOTED_RUNTIME_WIRING_NOT_READY",
    ):
        assert required in text
