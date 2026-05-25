from __future__ import annotations

from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import evaluate_deribit_manual_review_readiness
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

SUMMARY = Path("docs/crypto_core/DERIBIT_NEXT_BLOCKER_SUMMARY_55H.md")


def _normalized_summary_text() -> str:
    return " ".join(SUMMARY.read_text(encoding="utf-8").split())


def test_phase55h_next_blocker_summary_records_post_patch_state() -> None:
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
    assert "`phase54_telemetry_audit_verdict` | `PASS`" in text
    assert "`phase55_promotion_readiness_verdict` | `READY_FOR_OPERATOR_REVIEW`" in text


def test_phase55h_next_blocker_summary_records_readiness_but_no_promotion_or_live_scope() -> None:
    text = _normalized_summary_text()

    for required in (
        "`ready_for_operator_promotion_review` | `True`",
        "`promotion_granted` | `False`",
        "`live_ready` | `False`",
        "`shadow_ready` | `False`",
        "`fill_rate` | `1.0`",
        "`rejection_rate` | `0.0`",
        "`session_acceptance_rate` | `1.0`",
        "`ledger_mutation_rate` | `1.0`",
        "`automatic_paper_loop_ready` | `NO`",
        "`scheduler_ready` | `NO`",
    ):
        assert required in text


def test_phase55h_next_blocker_summary_points_to_operator_promotion_proposal() -> None:
    text = _normalized_summary_text()

    assert "OPERATOR_PROMOTION_REVIEW_PROPOSAL_NOT_READY" in text
    assert "must remain proposal-only" in text
