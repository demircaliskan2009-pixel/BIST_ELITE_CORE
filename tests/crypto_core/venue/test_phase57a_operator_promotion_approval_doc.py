from __future__ import annotations

from pathlib import Path

from tests.crypto_core.venue.test_phase57b_operator_promotion_approval_artifact import APPROVAL_METADATA

DOC = Path("docs/crypto_core/PAPER_PERFORMANCE_OPERATOR_PROMOTION_APPROVAL_EXECUTION_57A.md")


def test_phase57a_doc_records_operator_promotion_approval_execution_boundary() -> None:
    text = DOC.read_text(encoding="utf-8")

    for required in (
        "status: PAPER_PERFORMANCE_OPERATOR_PROMOTION_APPROVAL_EXECUTED",
        "scope: OPERATOR_PROMOTION_APPROVAL_METADATA_ARTIFACT_ONLY",
        "docs/crypto_core/DERIBIT_PAPER_PERFORMANCE_OPERATOR_PROMOTION_REVIEW_PROPOSAL_56B.json",
        "docs/crypto_core/DERIBIT_PAPER_PERFORMANCE_PROMOTION_READINESS_EVALUATION_55B.json",
        "`approval_status` | `APPROVED`",
        "`promotion_granted` | `False`",
        "`campaign_execution` | `False`",
        "NOT_approved_promotion_execution: true",
        "NOT_campaign_execution: true",
        "NOT_ledger_mutation: true",
        "NOT_scheduler: true",
        "NOT_automatic_paper_loop: true",
        "NOT_shadow_live_trading: true",
    ):
        assert required in text


def test_phase57a_doc_records_exact_supplied_approval_metadata() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert f"`operator_id` | `{APPROVAL_METADATA['operator_id']}`" in text
    assert f"`reviewed_at_iso` | `{APPROVAL_METADATA['reviewed_at_iso']}`" in text
    assert f"`approval_decision` | `{APPROVAL_METADATA['approval_decision']}`" in text
    assert f"`merge_policy_note` | `{APPROVAL_METADATA['merge_policy_note']}`" in text
    assert "`operator_metadata_source` | `explicit_user_approval_in_chat`" in text


def test_phase57a_doc_points_to_approved_promotion_execution_gate_not_grant() -> None:
    text = DOC.read_text(encoding="utf-8")
    normalized = " ".join(text.split())

    assert "APPROVED_PROMOTION_EXECUTION_NOT_READY" in text
    assert "This phase does not grant promotion" in normalized
    assert "does not authorize approved promotion execution" in text
