from __future__ import annotations

from pathlib import Path

from crypto_core.venue.public_feed_dialects import connector_ready_dialects
from tests.crypto_core.venue.test_phase58b_approved_paper_promotion_execution_artifact import _execution

SUMMARY = Path("docs/crypto_core/DERIBIT_NEXT_BLOCKER_SUMMARY_58H.md")


def _normalized_summary_text() -> str:
    return " ".join(SUMMARY.read_text(encoding="utf-8").split())


def test_phase58h_next_blocker_summary_records_current_readiness_state() -> None:
    text = SUMMARY.read_text(encoding="utf-8")

    assert len(connector_ready_dialects()) == 1
    assert "`accepted` | `True`" in text
    assert "`pending_rows` | `0`" in text
    assert "`deferred_rows` | `()`" in text
    assert "`connector_ready_dialects` | `1`" in text
    assert "`B1` | `READY_FOR_HUMAN_GATE`" in text
    for field in ("`B2` | `READY`", "`B3` | `READY`", "`B4` | `READY`", "`B5` | `READY`"):
        assert field in text


def test_phase58h_next_blocker_summary_records_paper_promotion_without_live_scope() -> None:
    text = _normalized_summary_text()
    execution = _execution()

    assert execution["promotion_granted"] is True
    for required in (
        "`promotion_execution_status` | `EXECUTED`",
        "`approved_action` | `APPROVED_PAPER_PROMOTION_EXECUTION`",
        "`promotion_granted` | `True`",
        "`promotion_scope` | `PAPER_ONLY_SIMULATION_ONLY`",
        "`paper_promoted` | `True`",
        "`live_ready` | `False`",
        "`shadow_ready` | `False`",
        "`campaign_execution` | `False`",
        "`ledger_mutation` | `False`",
        "`automatic_paper_loop_ready` | `NO`",
        "`scheduler_ready` | `NO`",
    ):
        assert required in text


def test_phase58h_next_blocker_summary_points_to_telemetry_gate() -> None:
    text = _normalized_summary_text()

    assert "PAPER_PROMOTION_EXECUTION_TELEMETRY_NOT_READY" in text
    assert "deterministic telemetry/audit" in text
