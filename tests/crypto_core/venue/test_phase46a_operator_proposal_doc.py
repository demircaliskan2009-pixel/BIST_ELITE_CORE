from __future__ import annotations

from pathlib import Path

DOC = Path("docs/crypto_core/BOUNDED_REPEATED_PAPER_CAMPAIGN_OPERATOR_PROPOSAL_46A.md")


def test_phase46a_doc_defines_operator_proposal_without_approval() -> None:
    text = DOC.read_text(encoding="utf-8")

    for required in (
        "status: BOUNDED_REPEATED_PAPER_CAMPAIGN_OPERATOR_PROPOSAL_READY",
        "docs/crypto_core/DERIBIT_PAPER_SESSION_PROMOTION_EVALUATION_45B.json",
        "docs/crypto_core/DERIBIT_REPEATED_HARD_CAPPED_SESSION_REPORT_PACK_44B.json",
        "docs/crypto_core/PAPER_SESSION_PROMOTION_CRITERIA_43A.md",
        "The proposal is NOT APPROVED YET",
        "approval_status=NOT_APPROVED",
    ):
        assert required in text


def test_phase46a_doc_records_scope_bounds_and_required_placeholders() -> None:
    text = DOC.read_text(encoding="utf-8")

    for required in (
        "public market data only",
        "paper-only",
        "explicit operator-triggered only",
        "`hard_cap` | `3`",
        "`per_session_max_trades` | `2`",
        "`max_sessions_proposed` | `3`",
        "`reviewer_id` | `<OPERATOR_REQUIRED>`",
        "`approval_decision` | `<OPERATOR_REQUIRED>`",
        "NOT_scheduler: true",
        "NOT_automatic_paper_loop: true",
        "NOT_shadow_live_trading: true",
    ):
        assert required in text
