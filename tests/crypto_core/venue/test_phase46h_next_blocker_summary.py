from __future__ import annotations

from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import evaluate_deribit_manual_review_readiness
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

SUMMARY = Path("docs/crypto_core/DERIBIT_NEXT_BLOCKER_SUMMARY_46H.md")


def _normalized_summary_text() -> str:
    return " ".join(SUMMARY.read_text(encoding="utf-8").split())


def test_phase46h_next_blocker_summary_records_post_patch_state() -> None:
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
    assert "`phase45_promotion_evaluation_status` | `READY_FOR_OPERATOR_REVIEW`" in text
    assert "`phase46_operator_proposal_status` | `READY_FOR_OPERATOR_REVIEW`" in text


def test_phase46h_next_blocker_summary_records_not_approved_and_no_live_scope() -> None:
    text = _normalized_summary_text()

    for required in (
        "`approval_status` | `NOT_APPROVED`",
        "`promotion_granted` | `False`",
        "`operator_approval_required` | `True`",
        "`live_ready` | `NO`",
        "`automatic_paper_loop_ready` | `NO`",
        "`scheduler_ready` | `NO`",
        "`hard_cap` | `3`",
        "`per_session_max_trades` | `2`",
        "`max_sessions_proposed` | `3`",
    ):
        assert required in text


def test_phase46h_next_blocker_summary_points_to_explicit_metadata_gate() -> None:
    text = _normalized_summary_text()

    assert "operator approval execution ONLY if the user explicitly provides complete approval metadata" in text
    assert "approval_status=NOT_APPROVED" in text
