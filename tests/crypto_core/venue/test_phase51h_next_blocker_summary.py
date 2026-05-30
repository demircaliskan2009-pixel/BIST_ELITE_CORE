from __future__ import annotations

from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import evaluate_deribit_manual_review_readiness
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

SUMMARY = Path("docs/crypto_core/DERIBIT_NEXT_BLOCKER_SUMMARY_51H.md")


def _normalized_summary_text() -> str:
    return " ".join(SUMMARY.read_text(encoding="utf-8").split())


def test_phase51h_next_blocker_summary_records_post_patch_state() -> None:
    text = SUMMARY.read_text(encoding="utf-8")
    readiness = evaluate_deribit_manual_review_readiness()

    assert readiness.accepted is True
    assert len(connector_ready_dialects()) == 1
    assert "`accepted` | `True`" in text
    assert "`evidence_review_complete` | `True`" in text
    assert "`connector_enablement_ready` | `True`" in text
    assert "`pending_rows` | `0`" in text
    assert "`deferred_rows` | `()`" in text
    assert "`connector_ready_dialects` | `1`" in text
    assert "`phase50_performance_evaluation_verdict` | `PASS`" in text
    assert "`phase51_proposal_status` | `READY_FOR_OPERATOR_REVIEW`" in text


def test_phase51h_next_blocker_summary_records_not_approved_and_no_live_scope() -> None:
    text = _normalized_summary_text()

    for required in (
        "`approval_status` | `NOT_APPROVED`",
        "`operator_metadata_required` | `True`",
        "`approval_decision` | `PLACEHOLDER_ONLY`",
        "`promotion_granted` | `False`",
        "`live_ready` | `False`",
        "`shadow_ready` | `False`",
        "`automatic_paper_loop_ready` | `NO`",
        "`scheduler_ready` | `NO`",
    ):
        assert required in text


def test_phase51h_next_blocker_summary_points_to_explicit_operator_approval_gate() -> None:
    text = _normalized_summary_text()

    assert "operator approval for paper performance only" in text
    assert "explicitly provides complete operator metadata" in text
    assert "approval_status=NOT_APPROVED" in text
