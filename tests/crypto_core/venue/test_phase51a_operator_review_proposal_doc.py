from __future__ import annotations

from pathlib import Path

DOC = Path("docs/crypto_core/PAPER_CAMPAIGN_PERFORMANCE_OPERATOR_REVIEW_PROPOSAL_51A.md")


def test_phase51a_doc_records_operator_review_proposal_without_approval() -> None:
    text = DOC.read_text(encoding="utf-8")

    for required in (
        "status: PAPER_CAMPAIGN_PERFORMANCE_OPERATOR_REVIEW_PROPOSAL_READY",
        "scope: OPERATOR_REVIEW_PROPOSAL_ONLY",
        "docs/crypto_core/DERIBIT_BOUNDED_PAPER_CAMPAIGN_PERFORMANCE_EVALUATION_50B.json",
        "`proposal_status` | `READY_FOR_OPERATOR_REVIEW`",
        "`approval_status` | `NOT_APPROVED`",
        "`operator_metadata_required` | `True`",
        "`approval_decision` | `PLACEHOLDER_ONLY`",
        "NOT_operator_approval_execution: true",
        "NOT_campaign_execution: true",
        "NOT_scheduler: true",
        "NOT_automatic_paper_loop: true",
        "NOT_shadow_live_trading: true",
    ):
        assert required in text


def test_phase51a_doc_records_required_placeholders_and_next_blocker() -> None:
    text = DOC.read_text(encoding="utf-8")

    for required in (
        "`reviewer_id` | `<OPERATOR_REQUIRED>`",
        "`reviewed_at_iso` | `<OPERATOR_REQUIRED>`",
        "`approval_scope` | `<OPERATOR_REQUIRED>`",
        "`approval_notes` | `<OPERATOR_REQUIRED>`",
        "Any non-placeholder metadata in Phase51 is invalid and must fail closed.",
        "operator approval for paper performance",
    ):
        assert required in text
