from __future__ import annotations

from pathlib import Path

DOC = Path("docs/crypto_core/BOUNDED_REPEATED_PAPER_CAMPAIGN_EXECUTION_GATE_48A.md")


def test_phase48a_doc_defines_campaign_execution_gate_from_phase47_approval() -> None:
    text = DOC.read_text(encoding="utf-8")

    for required in (
        "status: BOUNDED_REPEATED_PAPER_CAMPAIGN_EXECUTION_GATE_READY",
        "docs/crypto_core/DERIBIT_BOUNDED_REPEATED_PAPER_CAMPAIGN_APPROVAL_47B.json",
        "docs/crypto_core/DERIBIT_BOUNDED_REPEATED_PAPER_CAMPAIGN_OPERATOR_PROPOSAL_46B.json",
        "docs/crypto_core/DERIBIT_REPEATED_HARD_CAPPED_SESSION_REPORT_PACK_44B.json",
        "Phase48 adds the bounded repeated paper campaign execution gate",
        "Phase42 hard-capped paper session seam",
    ):
        assert required in text


def test_phase48a_doc_records_hard_bounds_and_no_live_scope() -> None:
    text = DOC.read_text(encoding="utf-8")

    for required in (
        "hard cap remains `3`",
        "`per_session_max_trades=2`",
        "`max_campaign_sessions<=3`",
        "explicit deterministic offline session fixtures only",
        "NOT_scheduler: true",
        "NOT_automatic_paper_loop: true",
        "NOT_shadow_live_trading: true",
    ):
        assert required in text
