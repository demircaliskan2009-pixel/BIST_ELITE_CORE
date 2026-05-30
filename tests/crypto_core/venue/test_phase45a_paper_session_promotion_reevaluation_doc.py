from __future__ import annotations

from pathlib import Path

DOC = Path("docs/crypto_core/PAPER_SESSION_PROMOTION_REEVALUATION_45A.md")


def test_phase45a_doc_defines_reevaluation_without_automatic_promotion() -> None:
    text = DOC.read_text(encoding="utf-8")

    for required in (
        "status: PAPER_SESSION_PROMOTION_REEVALUATION_REPORTED",
        "docs/crypto_core/DERIBIT_PAPER_SESSION_PROMOTION_READINESS_43B.json",
        "docs/crypto_core/DERIBIT_REPEATED_HARD_CAPPED_SESSION_REPORT_PACK_44B.json",
        "promotion_granted=false",
        "ready_for_operator_review=true",
        "live_ready=false",
        "operator approval worksheet/proposal",
    ):
        assert required in text


def test_phase45a_doc_records_matrix_and_no_live_scope() -> None:
    text = DOC.read_text(encoding="utf-8")

    for required in (
        "evidence count",
        "hard-cap compliance",
        "per-session trade-count compliance",
        "idempotency and duplicate protection",
        "ledger mutation consistency",
        "no-live/no-private/no-execution invariants",
        "fail-closed negative cases",
        "NOT_scheduler: true",
        "NOT_automatic_paper_loop: true",
        "NOT_shadow_live_trading: true",
    ):
        assert required in text
