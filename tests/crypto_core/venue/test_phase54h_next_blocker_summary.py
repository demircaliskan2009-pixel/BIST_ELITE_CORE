from __future__ import annotations

from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import evaluate_deribit_manual_review_readiness
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

SUMMARY = Path("docs/crypto_core/DERIBIT_NEXT_BLOCKER_SUMMARY_54H.md")


def _normalized_summary_text() -> str:
    return " ".join(SUMMARY.read_text(encoding="utf-8").split())


def test_phase54h_next_blocker_summary_records_post_patch_state() -> None:
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
    assert "`phase53_execution_verdict` | `PASS`" in text
    assert "`phase54_telemetry_audit_verdict` | `PASS`" in text


def test_phase54h_next_blocker_summary_records_metrics_and_no_live_scope() -> None:
    text = _normalized_summary_text()

    for required in (
        "`campaign_execution_status` | `EXECUTED`",
        "`execution_mode` | `OFFLINE_DETERMINISTIC_PAPER_ONLY`",
        "`sessions_requested` | `3`",
        "`sessions_attempted` | `3`",
        "`sessions_accepted` | `3`",
        "`sessions_rejected` | `0`",
        "`aggregate_trades_requested` | `6`",
        "`aggregate_trades_filled` | `6`",
        "`aggregate_ledger_mutations` | `6`",
        "`fill_rate` | `1.0`",
        "`rejection_rate` | `0.0`",
        "`ledger_mutation_rate` | `1.0`",
        "`session_acceptance_rate` | `1.0`",
        "`avg_fills_per_session` | `2.0`",
        "`promotion_granted` | `False`",
        "`ready_for_live` | `False`",
        "`ready_for_shadow` | `False`",
        "`automatic_paper_loop_ready` | `NO`",
        "`scheduler_ready` | `NO`",
    ):
        assert required in text


def test_phase54h_next_blocker_summary_points_to_promotion_readiness_phase() -> None:
    text = _normalized_summary_text()

    assert "PAPER_PERFORMANCE_PROMOTION_READINESS_NOT_READY" in text
    assert "must remain evaluation-only" in text
