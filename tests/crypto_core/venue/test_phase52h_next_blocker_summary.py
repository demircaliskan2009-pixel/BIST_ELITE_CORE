from __future__ import annotations

from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import evaluate_deribit_manual_review_readiness
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

SUMMARY = Path("docs/crypto_core/DERIBIT_NEXT_BLOCKER_SUMMARY_52H.md")


def _normalized_summary_text() -> str:
    return " ".join(SUMMARY.read_text(encoding="utf-8").split())


def test_phase52h_next_blocker_summary_records_post_patch_state() -> None:
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
    assert "`phase50_performance_evaluation_verdict` | `PASS`" in text
    assert "`phase51_proposal_status` | `READY_FOR_OPERATOR_REVIEW`" in text
    assert "`phase52_approval_status` | `APPROVED`" in text


def test_phase52h_next_blocker_summary_records_approval_but_no_execution() -> None:
    text = _normalized_summary_text()

    for required in (
        "`approval_decision` | `APPROVE_PAPER_CAMPAIGN_PERFORMANCE`",
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


def test_phase52h_next_blocker_summary_points_to_approved_campaign_execution_gate() -> None:
    text = _normalized_summary_text()

    assert "APPROVED_PAPER_PERFORMANCE_CAMPAIGN_EXECUTION_NOT_READY" in text
    assert "must remain explicit, paper-only, simulation-only" in text
