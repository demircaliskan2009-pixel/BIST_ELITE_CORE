from __future__ import annotations

from pathlib import Path

from crypto_core.venue.deribit_operator_promotion_review_proposal import propose_deribit_operator_promotion_review
from crypto_core.venue.public_feed_dialects import connector_ready_dialects
from tests.crypto_core.venue.test_phase56b_operator_promotion_review_proposal_artifact import (
    _phase54_telemetry,
    _phase55_readiness,
)

SUMMARY = Path("docs/crypto_core/DERIBIT_NEXT_BLOCKER_SUMMARY_56H.md")


def _normalized_summary_text() -> str:
    return " ".join(SUMMARY.read_text(encoding="utf-8").split())


def test_phase56h_next_blocker_summary_records_post_patch_state() -> None:
    text = SUMMARY.read_text(encoding="utf-8")
    proposal = propose_deribit_operator_promotion_review(_phase55_readiness(), _phase54_telemetry())

    assert proposal.accepted is True
    assert len(connector_ready_dialects()) == 1
    assert "`accepted` | `True`" in text
    assert "`proposal_review_complete` | `True`" in text
    assert "`connector_enablement_ready` | `True`" in text
    assert "`pending_rows` | `0`" in text
    assert "`deferred_rows` | `()`" in text
    assert "`connector_ready_dialects` | `1`" in text
    assert "`source_phase55_promotion_readiness_verdict` | `READY_FOR_OPERATOR_REVIEW`" in text
    assert "`phase56_proposal_status` | `READY_FOR_OPERATOR_REVIEW`" in text


def test_phase56h_next_blocker_summary_records_not_approved_and_no_live_scope() -> None:
    text = _normalized_summary_text()

    for required in (
        "`proposal_type` | `OPERATOR_PROMOTION_REVIEW`",
        "`approval_status` | `NOT_APPROVED`",
        "`operator_metadata_required` | `True`",
        "`approval_decision` | `PLACEHOLDER_ONLY`",
        "`promotion_granted` | `False`",
        "`ready_for_live` | `False`",
        "`ready_for_shadow` | `False`",
        "`automatic_paper_loop_ready` | `NO`",
        "`scheduler_ready` | `NO`",
    ):
        assert required in text


def test_phase56h_next_blocker_summary_points_to_explicit_operator_promotion_approval_gate() -> None:
    text = _normalized_summary_text()

    assert "OPERATOR_PROMOTION_APPROVAL_NOT_READY" in text
    assert "must remain proposal-only" in text
    assert "operator promotion approval metadata" in text
