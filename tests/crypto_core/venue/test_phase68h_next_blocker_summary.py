from __future__ import annotations

from pathlib import Path

from crypto_core.venue.public_feed_dialects import connector_ready_dialects
from tests.crypto_core.venue.test_phase68b_approved_paper_runtime_start_artifact import _execution

SUMMARY = Path("docs/crypto_core/DERIBIT_NEXT_BLOCKER_SUMMARY_68H.md")


def _normalized_summary_text() -> str:
    return " ".join(SUMMARY.read_text(encoding="utf-8").split())


def test_phase68h_next_blocker_summary_records_current_readiness_state() -> None:
    text = SUMMARY.read_text(encoding="utf-8")

    assert len(connector_ready_dialects()) == 1
    assert "`accepted` | `True`" in text
    assert "`pending_rows` | `0`" in text
    assert "`deferred_rows` | `()`" in text
    assert "`connector_ready_dialects` | `1`" in text
    assert "`B1` | `READY_FOR_HUMAN_GATE`" in text
    for field in ("`B2` | `READY`", "`B3` | `READY`", "`B4` | `READY`", "`B5` | `READY`"):
        assert field in text


def test_phase68h_next_blocker_summary_records_runtime_start_execution_state() -> None:
    text = _normalized_summary_text()
    artifact = _execution()

    assert artifact["runtime_start_execution_status"] == "EXECUTED"
    for required in (
        "`approval_status` | `APPROVED`",
        "`approval_decision` | `APPROVE_PAPER_RUNTIME_START_REVIEW`",
        "`runtime_start_approved` | `True`",
        "`runtime_start_execution_status` | `EXECUTED`",
        "`runtime_enabled` | `True`",
        "`runtime_started` | `True`",
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


def test_phase68h_next_blocker_summary_points_to_runtime_start_telemetry_gate() -> None:
    text = _normalized_summary_text()

    assert "PAPER_RUNTIME_START_TELEMETRY_NOT_READY" in text
    assert "started in paper metadata only" in text
    assert "no-live" in text
