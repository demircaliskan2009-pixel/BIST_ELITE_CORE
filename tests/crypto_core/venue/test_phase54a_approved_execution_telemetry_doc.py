from __future__ import annotations

from pathlib import Path

DOC = Path("docs/crypto_core/APPROVED_PAPER_PERFORMANCE_EXECUTION_TELEMETRY_AUDIT_54A.md")


def test_phase54a_doc_records_telemetry_audit_boundary() -> None:
    text = DOC.read_text(encoding="utf-8")

    for required in (
        "status: APPROVED_PAPER_PERFORMANCE_EXECUTION_TELEMETRY_AUDIT_READY",
        "scope: REPORT_ONLY_APPROVED_EXECUTION_TELEMETRY_AUDIT",
        "docs/crypto_core/DERIBIT_APPROVED_PAPER_PERFORMANCE_CAMPAIGN_EXECUTION_53B.json",
        "docs/crypto_core/DERIBIT_PAPER_CAMPAIGN_PERFORMANCE_OPERATOR_APPROVAL_52B.json",
        "NOT_new_campaign_execution: true",
        "NOT_ledger_mutation: true",
        "NOT_scheduler: true",
        "NOT_automatic_paper_loop: true",
        "NOT_shadow_live_trading: true",
    ):
        assert required in text


def test_phase54a_doc_records_metrics_and_fail_closed_requirements() -> None:
    text = DOC.read_text(encoding="utf-8")

    for required in (
        "`fill_rate` | `1.0`",
        "`rejection_rate` | `0.0`",
        "`ledger_mutation_rate` | `1.0`",
        "`session_acceptance_rate` | `1.0`",
        "`avg_fills_per_session` | `2.0`",
        "`connector_ready_dialects_count=1`",
        "`PAPER_PERFORMANCE_PROMOTION_READINESS_NOT_READY`",
    ):
        assert required in text


def test_phase54a_doc_does_not_grant_promotion_or_live_readiness() -> None:
    text = DOC.read_text(encoding="utf-8")
    normalized = " ".join(text.split())

    assert "does not grant promotion" in text
    assert "must not grant promotion or mark live/shadow readiness automatically" in normalized
