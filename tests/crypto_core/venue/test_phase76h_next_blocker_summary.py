from __future__ import annotations

from pathlib import Path

from crypto_core.venue.public_feed_dialects import connector_ready_dialects
from tests.crypto_core.venue.test_phase76b_paper_runtime_heartbeat_execution_post_audit_artifact import _json

SUMMARY = Path("docs/crypto_core/DERIBIT_NEXT_BLOCKER_SUMMARY_76H.md")
ARTIFACT = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_EXECUTION_POST_AUDIT_76B.json")


def _normalized_summary_text() -> str:
    return " ".join(SUMMARY.read_text(encoding="utf-8").split())


def test_phase76h_summary_records_current_readiness_state() -> None:
    text = SUMMARY.read_text(encoding="utf-8")

    assert len(connector_ready_dialects()) == 1
    assert "`accepted` | `True`" in text
    assert "`pending_rows` | `0`" in text
    assert "`deferred_rows` | `()`" in text
    assert "`connector_ready_dialects` | `1`" in text
    assert "`B1` | `READY_FOR_HUMAN_GATE`" in text


def test_phase76h_summary_records_post_audit_state() -> None:
    text = _normalized_summary_text()
    artifact = _json(ARTIFACT)

    assert artifact["heartbeat_execution_post_audit_status"] == "PASS"
    for required in (
        "`heartbeat_execution_post_audit_status` | `PASS`",
        "`heartbeat_execution_telemetry_status` | `PASS`",
        "`heartbeat_execution_status` | `EXECUTED`",
        "`execution_mode` | `APPROVED_PAPER_RUNTIME_HEARTBEAT_ONLY`",
        "`approval_status` | `APPROVED`",
        "`operator_id` | `demir_operator`",
        "`approval_scope` | `PAPER_ONLY_SIMULATION_ONLY`",
        "`runtime_enabled` | `True`",
        "`runtime_started` | `True`",
        "`runtime_loop_started` | `False`",
        "`runtime_order_routing_enabled` | `False`",
        "`campaign_execution` | `False`",
        "`session_execution` | `False`",
        "`run_execution` | `False`",
        "`ledger_mutation` | `False`",
    ):
        assert required in text


def test_phase76h_summary_points_to_next_blocker() -> None:
    text = _normalized_summary_text()

    assert "PAPER_RUNTIME_HEARTBEAT_EXECUTION_POST_AUDIT_REPORT_NOT_READY" in text
