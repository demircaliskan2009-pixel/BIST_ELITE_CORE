from __future__ import annotations

from pathlib import Path

from tests.crypto_core.venue.test_phase47b_operator_approval_artifact import APPROVAL_METADATA

DOC = Path("docs/crypto_core/DERIBIT_BOUNDED_REPEATED_PAPER_CAMPAIGN_APPROVAL_EXECUTION_47A.md")


def test_phase47a_doc_records_operator_approval_execution_boundary() -> None:
    text = DOC.read_text(encoding="utf-8")

    for required in (
        "status: BOUNDED_REPEATED_PAPER_CAMPAIGN_APPROVAL_EXECUTED",
        "scope: OPERATOR_APPROVAL_EXECUTION_ARTIFACT_ONLY",
        "docs/crypto_core/DERIBIT_BOUNDED_REPEATED_PAPER_CAMPAIGN_OPERATOR_PROPOSAL_46B.json",
        "docs/crypto_core/DERIBIT_PAPER_SESSION_PROMOTION_EVALUATION_45B.json",
        "docs/crypto_core/DERIBIT_REPEATED_HARD_CAPPED_SESSION_REPORT_PACK_44B.json",
        "`approval_status` | `APPROVED`",
        "`bounded_repeated_paper_campaign_approved` | `True`",
        "`promotion_granted` | `False`",
        "NOT_campaign_execution: true",
        "NOT_scheduler: true",
        "NOT_automatic_paper_loop: true",
        "NOT_shadow_live_trading: true",
    ):
        assert required in text


def test_phase47a_doc_records_exact_supplied_approval_metadata() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert f"`reviewer_id` | `{APPROVAL_METADATA['reviewer_id']}`" in text
    assert f"`reviewed_at_iso` | `{APPROVAL_METADATA['reviewed_at_iso']}`" in text
    assert f"`approval_decision` | `{APPROVAL_METADATA['approval_decision']}`" in text
    assert APPROVAL_METADATA["approval_scope"] in text
    assert APPROVAL_METADATA["approval_notes"] in text


def test_phase47a_doc_points_to_execution_gate_not_campaign_execution() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert "BOUNDED_REPEATED_PAPER_CAMPAIGN_EXECUTION_GATE_NOT_READY" in text
    assert "This phase does not execute the approved campaign" in text
    assert "It is not live readiness" in text
