from __future__ import annotations

from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import evaluate_deribit_manual_review_readiness
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

SUMMARY = Path("docs/crypto_core/DERIBIT_NEXT_BLOCKER_SUMMARY_49H.md")


def _normalized_summary_text() -> str:
    return " ".join(SUMMARY.read_text(encoding="utf-8").split())


def test_phase49h_next_blocker_summary_records_post_patch_state() -> None:
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
    assert "`phase47_approval_status` | `APPROVED`" in text


def test_phase49h_next_blocker_summary_records_audit_state_but_no_live_scope() -> None:
    text = _normalized_summary_text()

    for required in (
        "`audit_verdict` | `PASS`",
        "`campaign_execution_verdict` | `PASS`",
        "`campaign_telemetry_audit_status` | `COMPLETE`",
        "`report_only` | `YES`",
        "`sessions_requested` | `3`",
        "`sessions_attempted` | `3`",
        "`sessions_accepted` | `3`",
        "`sessions_rejected` | `0`",
        "`aggregate_trades_requested` | `6`",
        "`aggregate_trades_filled` | `6`",
        "`aggregate_ledger_mutations` | `6`",
        "`hard_cap` | `3`",
        "`per_session_max_trades` | `2`",
        "`live_ready` | `NO`",
        "`automatic_paper_loop_ready` | `NO`",
        "`scheduler_ready` | `NO`",
    ):
        assert required in text


def test_phase49h_next_blocker_summary_points_to_paper_campaign_performance_evaluation() -> None:
    text = _normalized_summary_text()

    assert "does not execute another campaign, session, or run" in text
    assert "does not mutate ledger state" in text
    assert "paper campaign performance evaluation only" in text
