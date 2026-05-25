from __future__ import annotations

from pathlib import Path

DOC = Path("docs/crypto_core/APPROVED_PAPER_PERFORMANCE_CAMPAIGN_EXECUTION_53A.md")


def test_phase53a_doc_records_execution_boundary() -> None:
    text = DOC.read_text(encoding="utf-8")

    for required in (
        "status: APPROVED_PAPER_PERFORMANCE_CAMPAIGN_EXECUTED",
        "scope: OFFLINE_DETERMINISTIC_PAPER_CAMPAIGN_EXECUTION_ONLY",
        "docs/crypto_core/DERIBIT_PAPER_CAMPAIGN_PERFORMANCE_OPERATOR_APPROVAL_52B.json",
        "docs/crypto_core/DERIBIT_BOUNDED_PAPER_CAMPAIGN_PERFORMANCE_EVALUATION_50B.json",
        "docs/crypto_core/DERIBIT_BOUNDED_REPEATED_PAPER_CAMPAIGN_EXECUTION_48B.json",
        "NOT_live_trading: true",
        "NOT_private_api: true",
        "NOT_exchange_orders: true",
        "NOT_execution_adapter: true",
        "NOT_strategy_alpha: true",
        "NOT_scheduler: true",
        "NOT_automatic_paper_loop: true",
        "NOT_shadow_live_trading: true",
    ):
        assert required in text


def test_phase53a_doc_records_exact_execution_metadata() -> None:
    text = DOC.read_text(encoding="utf-8")

    for required in (
        "`approval_status` | `APPROVED`",
        "`operator_id` | `demir_operator`",
        "`approval_decision` | `APPROVE_PAPER_CAMPAIGN_PERFORMANCE`",
        "`execution_mode` | `OFFLINE_DETERMINISTIC_PAPER_ONLY`",
        "`campaign_request_id` | `phase53-approved-paper-performance-campaign`",
        "`sessions_requested` | `3`",
        "`sessions_attempted` | `3`",
        "`sessions_accepted` | `3`",
        "`sessions_rejected` | `0`",
        "`aggregate_trades_requested` | `6`",
        "`aggregate_trades_filled` | `6`",
        "`aggregate_ledger_mutations` | `6`",
        "`hard_cap` | `3`",
        "`per_session_max_trades` | `2`",
    ):
        assert required in text


def test_phase53a_doc_points_to_execution_telemetry_blocker() -> None:
    text = " ".join(DOC.read_text(encoding="utf-8").split())

    assert "APPROVED_PAPER_PERFORMANCE_EXECUTION_TELEMETRY_NOT_READY" in text
    assert "does not authorize or enable live trading" in text
    assert "must remain report-only over this approved offline paper execution artifact" in text
