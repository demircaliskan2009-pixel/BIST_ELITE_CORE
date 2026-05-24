from __future__ import annotations

from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import evaluate_deribit_manual_review_readiness
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

SUMMARY = Path("docs/crypto_core/DERIBIT_NEXT_BLOCKER_SUMMARY_44H.md")


def _normalized_summary_text() -> str:
    return " ".join(SUMMARY.read_text(encoding="utf-8").split())


def test_phase44h_next_blocker_summary_records_post_patch_state() -> None:
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
    assert "`phase44_repeated_report_pack_status` | `PASS`" in text


def test_phase44h_next_blocker_summary_records_pack_counts_and_no_live_scope() -> None:
    text = _normalized_summary_text()

    for required in (
        "`hard_cap` | `3`",
        "`per_session_max_trades` | `2`",
        "`session_count` | `3`",
        "`aggregate_trades_requested` | `6`",
        "`aggregate_trades_rejected` | `0`",
        "`promotion_granted` | `False`",
        "`live_ready` | `NO`",
        "`automatic_paper_loop_ready` | `NO`",
        "`scheduler_ready` | `NO`",
    ):
        assert required in text


def test_phase44h_next_blocker_summary_points_to_next_safe_phase() -> None:
    text = _normalized_summary_text()

    assert "promotion criteria re-evaluation against the repeated report pack" in text
    assert "no scheduler, live trading, or shadow trading" in text
