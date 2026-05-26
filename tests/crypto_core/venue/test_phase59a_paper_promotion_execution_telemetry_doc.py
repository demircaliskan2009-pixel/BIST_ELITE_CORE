from __future__ import annotations

from pathlib import Path

DOC = Path("docs/crypto_core/PAPER_PROMOTION_EXECUTION_TELEMETRY_AUDIT_59A.md")


def test_phase59a_doc_exists_and_names_sources() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert "Phase 59A - Deribit Paper Promotion Execution Telemetry Audit" in text
    assert "DERIBIT_APPROVED_PAPER_PROMOTION_EXECUTION_58B.json" in text
    assert "DERIBIT_PAPER_PERFORMANCE_PROMOTION_READINESS_EVALUATION_55B.json" in text
    assert "`source_phase58_promotion_execution_status` | `EXECUTED`" in text
    assert "`source_phase58_approval_decision` | `APPROVE_PAPER_PROMOTION_REVIEW`" in text


def test_phase59a_doc_records_report_only_no_new_execution_boundary() -> None:
    text = " ".join(DOC.read_text(encoding="utf-8").split())

    for required in (
        "`telemetry_audit_status` | `AUDITED`",
        "`telemetry_audit_verdict` | `PASS`",
        "`execution_verdict` | `PASS`",
        "`promotion_granted` | `True`",
        "`report_only` | `True`",
        "`no_new_execution` | `True`",
        "NOT_new_campaign_execution: true",
        "NOT_new_ledger_mutation: true",
        "does not run campaign/session/run execution",
    ):
        assert required in text


def test_phase59a_doc_points_to_post_audit_next_blocker() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert "PAPER_PROMOTION_EXECUTION_POST_AUDIT_NOT_READY" in text
    assert "must remain deterministic and report-only" in text
