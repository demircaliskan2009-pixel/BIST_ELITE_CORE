from __future__ import annotations

from pathlib import Path

DOC = Path("docs/crypto_core/PAPER_SESSION_PROMOTION_CRITERIA_43A.md")


def test_phase43a_doc_defines_promotion_readiness_without_promotion() -> None:
    text = DOC.read_text(encoding="utf-8")

    for required in (
        "status: PAPER_SESSION_PROMOTION_READINESS_REPORTED",
        "docs/crypto_core/DERIBIT_HARD_CAPPED_PAPER_SESSION_ARTIFACT_42B.json",
        "docs/crypto_core/DERIBIT_BOUNDED_PAPER_RUN_TELEMETRY_REPORT_41B.json",
        "Promotion is NOT granted in this phase",
        "repeated deterministic hard-capped session report pack",
    ):
        assert required in text


def test_phase43a_doc_records_required_criteria_categories_and_no_live_scope() -> None:
    text = DOC.read_text(encoding="utf-8")

    for required in (
        "safety gates",
        "ledger correctness",
        "idempotency",
        "rejection accounting",
        "no-live/no-private invariants",
        "run/report determinism",
        "max loss, max reject, and max mutation anomaly thresholds",
        "NOT_scheduler: true",
        "NOT_automatic_paper_loop: true",
        "NOT_shadow_live_trading: true",
    ):
        assert required in text
