from __future__ import annotations

from pathlib import Path

from tests.crypto_core.venue.test_phase52b_operator_approval_artifact import APPROVAL_METADATA

DOC = Path("docs/crypto_core/PAPER_CAMPAIGN_PERFORMANCE_OPERATOR_APPROVAL_EXECUTION_52A.md")


def test_phase52a_doc_records_operator_approval_execution_boundary() -> None:
    text = DOC.read_text(encoding="utf-8")

    for required in (
        "status: PAPER_CAMPAIGN_PERFORMANCE_OPERATOR_APPROVAL_EXECUTED",
        "scope: OPERATOR_APPROVAL_METADATA_ARTIFACT_ONLY",
        "docs/crypto_core/DERIBIT_PAPER_CAMPAIGN_PERFORMANCE_OPERATOR_REVIEW_PROPOSAL_51B.json",
        "docs/crypto_core/DERIBIT_BOUNDED_PAPER_CAMPAIGN_PERFORMANCE_EVALUATION_50B.json",
        "docs/crypto_core/DERIBIT_BOUNDED_PAPER_CAMPAIGN_TELEMETRY_AUDIT_49B.json",
        "`approval_status` | `APPROVED`",
        "`promotion_granted` | `False`",
        "`campaign_execution` | `False`",
        "NOT_campaign_execution: true",
        "NOT_ledger_mutation: true",
        "NOT_scheduler: true",
        "NOT_automatic_paper_loop: true",
        "NOT_shadow_live_trading: true",
    ):
        assert required in text


def test_phase52a_doc_records_exact_supplied_approval_metadata() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert f"`operator_id` | `{APPROVAL_METADATA['operator_id']}`" in text
    assert f"`reviewed_at_iso` | `{APPROVAL_METADATA['reviewed_at_iso']}`" in text
    assert f"`approval_decision` | `{APPROVAL_METADATA['approval_decision']}`" in text
    assert "`operator_metadata_source` | `explicit_user_approval_in_chat`" in text


def test_phase52a_doc_points_to_execution_gate_not_campaign_execution() -> None:
    text = DOC.read_text(encoding="utf-8")
    normalized = " ".join(text.split())

    assert "APPROVED_PAPER_PERFORMANCE_CAMPAIGN_EXECUTION_NOT_READY" in text
    assert "This phase does not execute the approved campaign" in normalized
    assert "does not authorize campaign/session/run execution" in text
