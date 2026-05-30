from __future__ import annotations

from pathlib import Path

from crypto_core.venue.public_feed_dialects import connector_ready_dialects
from tests.crypto_core.venue.test_phase67b_paper_runtime_start_approval_artifact import _approval

SUMMARY = Path("docs/crypto_core/DERIBIT_NEXT_BLOCKER_SUMMARY_67H.md")


def _normalized_summary_text() -> str:
    return " ".join(SUMMARY.read_text(encoding="utf-8").split())


def test_phase67h_next_blocker_summary_records_current_readiness_state() -> None:
    text = SUMMARY.read_text(encoding="utf-8")

    assert len(connector_ready_dialects()) == 1
    assert "`accepted` | `True`" in text
    assert "`pending_rows` | `0`" in text
    assert "`deferred_rows` | `()`" in text
    assert "`connector_ready_dialects` | `1`" in text
    assert "`B1` | `READY_FOR_HUMAN_GATE`" in text
    for field in ("`B2` | `READY`", "`B3` | `READY`", "`B4` | `READY`", "`B5` | `READY`"):
        assert field in text


def test_phase67h_next_blocker_summary_records_approval_without_runtime_start() -> None:
    text = _normalized_summary_text()
    approval = _approval()

    assert approval["approval_status"] == "APPROVED"
    for required in (
        "`proposal_status` | `READY_FOR_OPERATOR_REVIEW`",
        "`approval_status` | `APPROVED`",
        "`approval_decision` | `APPROVE_PAPER_RUNTIME_START_REVIEW`",
        "`runtime_start_approved` | `True`",
        "`runtime_enabled` | `True`",
        "`runtime_started` | `False`",
        "`paper_promoted` | `True`",
        "`promotion_granted` | `True`",
        "`promotion_scope` | `PAPER_ONLY_SIMULATION_ONLY`",
        "`live_ready` | `False`",
        "`shadow_ready` | `False`",
        "`campaign_execution` | `False`",
        "`ledger_mutation` | `False`",
        "`automatic_paper_loop_ready` | `NO`",
        "`scheduler_ready` | `NO`",
    ):
        assert required in text


def test_phase67h_next_blocker_summary_points_to_start_execution_gate() -> None:
    text = _normalized_summary_text()

    assert "APPROVED_PAPER_RUNTIME_START_EXECUTION_NOT_READY" in text
    assert "does not start runtime" in text
    assert "runtime remains enabled and not started" in text
