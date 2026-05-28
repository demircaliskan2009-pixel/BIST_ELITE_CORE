from __future__ import annotations

from pathlib import Path

from crypto_core.venue.public_feed_dialects import connector_ready_dialects
from tests.crypto_core.venue.test_phase69b_paper_runtime_start_telemetry_artifact import _artifact

SUMMARY = Path("docs/crypto_core/DERIBIT_NEXT_BLOCKER_SUMMARY_69H.md")


def _normalized_summary_text() -> str:
    return " ".join(SUMMARY.read_text(encoding="utf-8").split())


def test_phase69h_next_blocker_summary_records_current_readiness_state() -> None:
    text = SUMMARY.read_text(encoding="utf-8")

    assert len(connector_ready_dialects()) == 1
    assert "`accepted` | `True`" in text
    assert "`pending_rows` | `0`" in text
    assert "`deferred_rows` | `()`" in text
    assert "`connector_ready_dialects` | `1`" in text
    assert "`B1` | `READY_FOR_HUMAN_GATE`" in text
    for field in ("`B2` | `READY`", "`B3` | `READY`", "`B4` | `READY`", "`B5` | `READY`"):
        assert field in text


def test_phase69h_next_blocker_summary_records_runtime_start_telemetry_state() -> None:
    text = _normalized_summary_text()
    artifact = _artifact()

    assert artifact["runtime_start_telemetry_status"] == "PASS"
    for required in (
        "`source_phase68_runtime_start_execution_status` | `EXECUTED`",
        "`runtime_start_telemetry_status` | `PASS`",
        "`runtime_enabled` | `True`",
        "`runtime_started` | `True`",
        "`runtime_mode` | `PAPER_ONLY_PASSIVE_STARTED`",
        "`runtime_loop_started` | `False`",
        "`runtime_order_routing_enabled` | `False`",
        "`promotion_scope` | `PAPER_ONLY_SIMULATION_ONLY`",
        "`live_ready` | `False`",
        "`shadow_ready` | `False`",
        "`scheduler_enabled` | `False`",
        "`auto_loop_enabled` | `False`",
        "`campaign_execution` | `False`",
        "`session_execution` | `False`",
        "`run_execution` | `False`",
        "`ledger_mutation` | `False`",
        "`automatic_paper_loop_ready` | `NO`",
        "`scheduler_ready` | `NO`",
    ):
        assert required in text


def test_phase69h_next_blocker_summary_points_to_operator_triggered_heartbeat_gate() -> None:
    text = _normalized_summary_text()

    assert "PAPER_RUNTIME_OPERATOR_TRIGGERED_HEARTBEAT_NOT_READY" in text
    assert "no-live and no-order-routing boundary" in text
