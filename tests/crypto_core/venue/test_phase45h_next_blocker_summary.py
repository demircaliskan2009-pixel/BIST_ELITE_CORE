from __future__ import annotations

from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import evaluate_deribit_manual_review_readiness
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

SUMMARY = Path("docs/crypto_core/DERIBIT_NEXT_BLOCKER_SUMMARY_45H.md")


def _normalized_summary_text() -> str:
    return " ".join(SUMMARY.read_text(encoding="utf-8").split())


def test_phase45h_next_blocker_summary_records_post_patch_state() -> None:
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
    assert "`phase44_repeated_report_pack_status` | `PASS`" in text
    assert "`phase45_promotion_evaluation_status` | `READY_FOR_OPERATOR_REVIEW`" in text


def test_phase45h_next_blocker_summary_records_operator_review_and_no_live_scope() -> None:
    text = _normalized_summary_text()

    for required in (
        "`promotion_verdict` | `READY_FOR_OPERATOR_REVIEW`",
        "`promotion_granted` | `False`",
        "`operator_approval_required` | `True`",
        "`live_ready` | `NO`",
        "`automatic_paper_loop_ready` | `NO`",
        "`scheduler_ready` | `NO`",
        "`hard_cap` | `3`",
        "`evaluated_session_count` | `3`",
        "`evaluated_max_session_trades` | `2`",
    ):
        assert required in text


def test_phase45h_next_blocker_summary_points_to_next_safe_phase() -> None:
    text = _normalized_summary_text()

    assert "operator approval/proposal for a bounded repeated paper campaign" in text
    assert "no scheduler, live trading, or shadow trading" in text
