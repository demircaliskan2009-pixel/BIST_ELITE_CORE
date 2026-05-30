from __future__ import annotations

from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import evaluate_deribit_manual_review_readiness
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

SUMMARY = Path("docs/crypto_core/DERIBIT_NEXT_BLOCKER_SUMMARY_42H.md")


def _normalized_summary_text() -> str:
    return " ".join(SUMMARY.read_text(encoding="utf-8").split())


def test_phase42h_next_blocker_summary_records_post_patch_state() -> None:
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
    assert "`phase40_bounded_paper_run_harness_status` | `READY`" in text
    assert "`phase41_telemetry_reporting_status` | `PASS`" in text
    assert "`phase42_hard_capped_session_status` | `READY`" in text


def test_phase42h_next_blocker_summary_records_session_bounds_and_no_live_scope() -> None:
    text = _normalized_summary_text()

    for required in (
        "`session_verdict` | `PASS`",
        "`hard_cap` | `3`",
        "`max_session_trades` | `2`",
        "`trades_requested` | `2`",
        "`trades_attempted` | `2`",
        "`trades_filled` | `2`",
        "`trades_rejected` | `0`",
        "`live_ready` | `NO`",
        "`automatic_paper_loop_ready` | `NO`",
        "`scheduler_ready` | `NO`",
        "`paper_session_promotion_criteria_ready` | `NO`",
    ):
        assert required in text


def test_phase42h_next_blocker_summary_points_to_next_safe_phase() -> None:
    text = _normalized_summary_text()

    assert "repeated hard-capped session telemetry plus promotion criteria" in text
    assert "Scheduler-driven operation, live trading, and shadow trading remain out of scope" in text
