from __future__ import annotations

from pathlib import Path

from crypto_core.venue.public_feed_dialects import connector_ready_dialects
from tests.crypto_core.venue.test_phase57b_operator_promotion_approval_artifact import _approval

SUMMARY = Path("docs/crypto_core/DERIBIT_NEXT_BLOCKER_SUMMARY_57H.md")


def _normalized_summary_text() -> str:
    return " ".join(SUMMARY.read_text(encoding="utf-8").split())


def test_phase57h_next_blocker_summary_records_post_patch_state() -> None:
    text = SUMMARY.read_text(encoding="utf-8")
    approval = _approval()

    assert approval["approval_status"] == "APPROVED"
    assert len(connector_ready_dialects()) == 1
    assert "`accepted` | `True`" in text
    assert "`approval_complete` | `True`" in text
    assert "`connector_enablement_ready` | `True`" in text
    assert "`pending_rows` | `0`" in text
    assert "`deferred_rows` | `()`" in text
    assert "`connector_ready_dialects` | `1`" in text
    assert "`source_phase55_promotion_readiness_verdict` | `READY_FOR_OPERATOR_REVIEW`" in text
    assert "`phase56_proposal_status` | `READY_FOR_OPERATOR_REVIEW`" in text
    assert "`phase57_approval_status` | `APPROVED`" in text


def test_phase57h_next_blocker_summary_records_approval_but_no_execution_or_live_scope() -> None:
    text = _normalized_summary_text()

    for required in (
        "`approval_decision` | `APPROVE_PAPER_PROMOTION_REVIEW`",
        "`operator_id` | `demir_operator`",
        "`merge_policy_note` | `MERGE_POLICY_VIOLATION_RECORDED`",
        "`promotion_granted` | `False`",
        "`campaign_execution` | `False`",
        "`session_execution` | `False`",
        "`run_execution` | `False`",
        "`ledger_mutated` | `False`",
        "`live_ready` | `False`",
        "`shadow_ready` | `False`",
        "`automatic_paper_loop_ready` | `NO`",
        "`scheduler_ready` | `NO`",
    ):
        assert required in text


def test_phase57h_next_blocker_summary_points_to_approved_promotion_execution_gate() -> None:
    text = _normalized_summary_text()

    assert "APPROVED_PROMOTION_EXECUTION_NOT_READY" in text
    assert "MERGE_POLICY_VIOLATION_RECORDED" in text
    assert "must remain approval-metadata-only" in text
