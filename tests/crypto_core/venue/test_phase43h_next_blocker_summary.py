from __future__ import annotations

from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import evaluate_deribit_manual_review_readiness
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

SUMMARY = Path("docs/crypto_core/DERIBIT_NEXT_BLOCKER_SUMMARY_43H.md")


def _normalized_summary_text() -> str:
    return " ".join(SUMMARY.read_text(encoding="utf-8").split())


def test_phase43h_next_blocker_summary_records_post_patch_state() -> None:
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
    assert "`phase42_hard_capped_session_status` | `READY`" in text
    assert "`phase43_promotion_readiness_status` | `NOT_READY`" in text


def test_phase43h_next_blocker_summary_records_promotion_not_ready_and_no_live_scope() -> None:
    text = _normalized_summary_text()

    for required in (
        "`promotion_verdict` | `NOT_READY`",
        "`promotion_reason` | `PAPER_PROMOTION_REQUIRES_REPEATED_SESSION_EVIDENCE`",
        "`repeated_session_campaign_ready` | `False`",
        "`hard_cap` | `3`",
        "`evaluated_max_session_trades` | `2`",
        "`evaluated_sessions` | `1`",
        "`required_future_sessions_minimum` | `3`",
        "`live_ready` | `NO`",
        "`automatic_paper_loop_ready` | `NO`",
        "`scheduler_ready` | `NO`",
        "`paper_session_promotion_ready` | `NO`",
    ):
        assert required in text


def test_phase43h_next_blocker_summary_points_to_next_safe_phase() -> None:
    text = _normalized_summary_text()

    assert "repeated deterministic hard-capped session report pack" in text
    assert "no scheduler, live trading, or shadow trading" in text
