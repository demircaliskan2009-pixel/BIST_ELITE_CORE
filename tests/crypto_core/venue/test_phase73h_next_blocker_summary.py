from __future__ import annotations

from pathlib import Path

from crypto_core.venue.public_feed_dialects import connector_ready_dialects
from tests.crypto_core.venue.test_phase73b_paper_runtime_heartbeat_operator_approval_artifact import _json

SUMMARY = Path("docs/crypto_core/DERIBIT_NEXT_BLOCKER_SUMMARY_73H.md")
ARTIFACT = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_OPERATOR_APPROVAL_73B.json")


def _normalized_summary_text() -> str:
    return " ".join(SUMMARY.read_text(encoding="utf-8").split())


def test_phase73h_summary_records_current_readiness_state() -> None:
    text = SUMMARY.read_text(encoding="utf-8")

    assert len(connector_ready_dialects()) == 1
    assert "`accepted` | `True`" in text
    assert "`pending_rows` | `0`" in text
    assert "`deferred_rows` | `()`" in text
    assert "`connector_ready_dialects` | `1`" in text
    assert "`B1` | `READY_FOR_HUMAN_GATE`" in text


def test_phase73h_summary_records_approval_state() -> None:
    text = _normalized_summary_text()
    artifact = _json(ARTIFACT)

    assert artifact["approval_status"] == "APPROVED"
    for required in (
        "`proposal_status` | `READY_FOR_OPERATOR_REVIEW`",
        "`approval_status` | `APPROVED`",
        "`operator_metadata_required` | `false`",
        "`operator_id` | `demir_operator`",
        "`reviewed_at_iso` | `2026-05-28T20:04:43Z`",
        "`approval_decision` | `APPROVE_PAPER_RUNTIME_HEARTBEAT_REVIEW`",
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


def test_phase73h_summary_points_to_next_blocker() -> None:
    text = _normalized_summary_text()

    assert "APPROVED_PAPER_RUNTIME_HEARTBEAT_EXECUTION_NOT_READY" in text
