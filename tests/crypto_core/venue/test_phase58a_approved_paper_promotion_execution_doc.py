from __future__ import annotations

from pathlib import Path

DOC = Path("docs/crypto_core/APPROVED_PAPER_PROMOTION_EXECUTION_58A.md")


def test_phase58a_doc_exists_and_names_sources() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert "Phase 58A - Deribit Approved Paper Promotion Execution" in text
    assert "DERIBIT_PAPER_PERFORMANCE_OPERATOR_PROMOTION_APPROVAL_57B.json" in text
    assert "DERIBIT_PAPER_PERFORMANCE_PROMOTION_READINESS_EVALUATION_55B.json" in text
    assert "`approval_decision` | `APPROVE_PAPER_PROMOTION_REVIEW`" in text
    assert "`operator_id` | `demir_operator`" in text


def test_phase58a_doc_records_paper_only_promotion_without_live_or_execution_scope() -> None:
    text = " ".join(DOC.read_text(encoding="utf-8").split())

    for required in (
        "`promotion_execution_status` | `EXECUTED`",
        "`approved_action` | `APPROVED_PAPER_PROMOTION_EXECUTION`",
        "`promotion_granted` | `True`",
        "`promotion_scope` | `PAPER_ONLY_SIMULATION_ONLY`",
        "`live_ready` | `False`",
        "`shadow_ready` | `False`",
        "`campaign_execution` | `False`",
        "`ledger_mutation` | `False`",
        "does not execute a campaign, session, or run",
        "does not mutate the ledger",
    ):
        assert required in text
