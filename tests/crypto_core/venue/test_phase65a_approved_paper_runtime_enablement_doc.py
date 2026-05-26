from __future__ import annotations

from pathlib import Path

DOC = Path("docs/crypto_core/APPROVED_PAPER_RUNTIME_ENABLEMENT_EXECUTION_65A.md")


def test_phase65a_doc_records_required_sources_and_execution_result() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert DOC.exists()
    assert "APPROVED_PAPER_RUNTIME_ENABLEMENT_EXECUTION_READY" in text
    assert "`docs/crypto_core/DERIBIT_PAPER_RUNTIME_ENABLEMENT_OPERATOR_APPROVAL_64B.json`" in text
    assert "`docs/crypto_core/DERIBIT_PAPER_PROMOTED_RUNTIME_WIRING_62B.json`" in text
    assert "`runtime_enablement_execution_status` | `EXECUTED`" in text
    assert "`runtime_enabled` | `True`" in text
    assert "`runtime_started` | `False`" in text


def test_phase65a_doc_preserves_no_start_no_live_boundary() -> None:
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
        "PAPER_RUNTIME_START_PROPOSAL_NOT_READY",
    ):
        assert required in text
