from __future__ import annotations

from pathlib import Path

DOC = Path("docs/crypto_core/REPEATED_HARD_CAPPED_SESSION_REPORT_PACK_44A.md")


def test_phase44a_doc_defines_repeated_session_report_pack_without_promotion() -> None:
    text = DOC.read_text(encoding="utf-8")

    for required in (
        "status: REPEATED_HARD_CAPPED_SESSION_REPORT_PACK_REPORTED",
        "docs/crypto_core/DERIBIT_HARD_CAPPED_PAPER_SESSION_ARTIFACT_42B.json",
        "docs/crypto_core/DERIBIT_PAPER_SESSION_PROMOTION_READINESS_43B.json",
        "Phase44 report pack",
        "Promotion is NOT GRANTED in this phase",
        "promotion criteria re-evaluation",
    ):
        assert required in text


def test_phase44a_doc_records_hard_cap_operator_fixture_and_no_live_scope() -> None:
    text = DOC.read_text(encoding="utf-8")

    for required in (
        "hard cap remains `3`",
        "`max_session_trades=2`",
        "explicit offline fixture session summaries",
        "NOT_strategy_or_alpha_generation: true",
        "NOT_scheduler: true",
        "NOT_automatic_paper_loop: true",
        "NOT_shadow_live_trading: true",
    ):
        assert required in text
