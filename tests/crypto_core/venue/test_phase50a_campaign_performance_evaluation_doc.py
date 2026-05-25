from __future__ import annotations

from pathlib import Path

DOC = Path("docs/crypto_core/BOUNDED_PAPER_CAMPAIGN_PERFORMANCE_EVALUATION_50A.md")


def test_phase50a_doc_records_report_only_performance_boundary() -> None:
    text = DOC.read_text(encoding="utf-8")

    for required in (
        "status: BOUNDED_PAPER_CAMPAIGN_PERFORMANCE_EVALUATION_READY",
        "scope: REPORT_ONLY_CAMPAIGN_PERFORMANCE_EVALUATION",
        "docs/crypto_core/DERIBIT_BOUNDED_PAPER_CAMPAIGN_TELEMETRY_AUDIT_49B.json",
        "docs/crypto_core/DERIBIT_BOUNDED_REPEATED_PAPER_CAMPAIGN_EXECUTION_48B.json",
        "NOT_new_campaign_execution: true",
        "NOT_ledger_mutation: true",
        "NOT_promotion: true",
        "NOT_scheduler: true",
        "NOT_automatic_paper_loop: true",
        "NOT_shadow_live_trading: true",
    ):
        assert required in text


def test_phase50a_doc_records_metrics_and_next_blocker() -> None:
    text = DOC.read_text(encoding="utf-8")

    for required in (
        "`fill_rate` | `1.0`",
        "`reject_rate` | `0.0`",
        "`ledger_mutation_count` | `6`",
        "`session_acceptance_rate` | `1.0`",
        "`evaluation_sample_size` | `3`",
        "operator review for paper performance only",
    ):
        assert required in text
