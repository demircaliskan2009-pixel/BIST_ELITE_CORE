from __future__ import annotations

from pathlib import Path

DOC = Path("docs/crypto_core/PAPER_PERFORMANCE_PROMOTION_READINESS_EVALUATION_55A.md")


def test_phase55a_doc_records_promotion_readiness_boundary() -> None:
    text = DOC.read_text(encoding="utf-8")

    for required in (
        "status: PAPER_PERFORMANCE_PROMOTION_READINESS_EVALUATION_READY",
        "scope: REPORT_ONLY_PROMOTION_READINESS_EVALUATION",
        "docs/crypto_core/DERIBIT_APPROVED_PAPER_PERFORMANCE_EXECUTION_TELEMETRY_AUDIT_54B.json",
        "NOT_new_campaign_execution: true",
        "NOT_ledger_mutation: true",
        "NOT_promotion: true",
        "NOT_operator_approval_execution: true",
        "NOT_scheduler: true",
        "NOT_automatic_paper_loop: true",
        "NOT_shadow_live_trading: true",
    ):
        assert required in text


def test_phase55a_doc_records_criteria_and_metrics() -> None:
    text = DOC.read_text(encoding="utf-8")

    for required in (
        "`minimum_sessions_required` | `3`",
        "`zero_rejected_sessions_required` | `True`",
        "`duplicate_mutation_block_required` | `True`",
        "`no_live_scope_required` | `True`",
        "`no_private_execution_scope_required` | `True`",
        "`fill_rate` | `1.0`",
        "`rejection_rate` | `0.0`",
        "`session_acceptance_rate` | `1.0`",
        "`ledger_mutation_rate` | `1.0`",
    ):
        assert required in text


def test_phase55a_doc_points_to_operator_proposal_without_approval() -> None:
    text = " ".join(DOC.read_text(encoding="utf-8").split())

    assert "promotion_readiness_verdict=READY_FOR_OPERATOR_REVIEW" in text
    assert "does not grant promotion" in text
    assert "OPERATOR_PROMOTION_REVIEW_PROPOSAL_NOT_READY" in text
