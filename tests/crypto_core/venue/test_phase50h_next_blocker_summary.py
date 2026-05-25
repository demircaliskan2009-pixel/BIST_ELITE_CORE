from __future__ import annotations

from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import evaluate_deribit_manual_review_readiness
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

SUMMARY = Path("docs/crypto_core/DERIBIT_NEXT_BLOCKER_SUMMARY_50H.md")


def _normalized_summary_text() -> str:
    return " ".join(SUMMARY.read_text(encoding="utf-8").split())


def test_phase50h_next_blocker_summary_records_post_patch_state() -> None:
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
    assert "`phase49_audit_verdict` | `PASS`" in text
    assert "`performance_evaluation_verdict` | `PASS`" in text


def test_phase50h_next_blocker_summary_records_no_live_scope() -> None:
    text = _normalized_summary_text()

    for required in (
        "`ready_for_operator_review` | `True`",
        "`promotion_granted` | `False`",
        "`ready_for_live` | `False`",
        "`ready_for_shadow` | `False`",
        "`report_only` | `YES`",
        "`fill_rate` | `1.0`",
        "`reject_rate` | `0.0`",
        "`live_ready` | `NO`",
        "`automatic_paper_loop_ready` | `NO`",
        "`scheduler_ready` | `NO`",
        "`hard_cap` | `3`",
        "`per_session_max_trades` | `2`",
    ):
        assert required in text


def test_phase50h_next_blocker_summary_points_to_operator_review_proposal() -> None:
    text = _normalized_summary_text()

    assert "does not execute another campaign, session, or run" in text
    assert "does not mutate ledger state" in text
    assert "operator review proposal for paper performance" in text
