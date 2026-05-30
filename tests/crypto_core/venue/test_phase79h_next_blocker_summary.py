from __future__ import annotations

from pathlib import Path

from crypto_core.venue.public_feed_dialects import connector_ready_dialects
from tests.crypto_core.venue.test_phase79b_paper_runtime_heartbeat_provenance_gate_blocker_persistence_artifact import (
    _json,
)

SUMMARY = Path("docs/crypto_core/DERIBIT_NEXT_BLOCKER_SUMMARY_79H.md")
ARTIFACT = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_PROVENANCE_GATE_BLOCKER_PERSISTENCE_79B.json")


def _normalized_summary_text() -> str:
    return " ".join(SUMMARY.read_text(encoding="utf-8").split())


def test_phase79h_summary_records_current_readiness_state() -> None:
    text = SUMMARY.read_text(encoding="utf-8")

    assert len(connector_ready_dialects()) == 1
    assert "`accepted` | `True`" in text
    assert "`pending_rows` | `0`" in text
    assert "`deferred_rows` | `()`" in text
    assert "`connector_ready_dialects` | `1`" in text
    assert "`B1` | `READY_FOR_HUMAN_GATE`" in text
    assert "`B5` | `BLOCKED`" in text


def test_phase79h_summary_records_provenance_gate_blocker_persistence() -> None:
    text = _normalized_summary_text()
    artifact = _json(ARTIFACT)

    assert artifact["provenance_gate_blocker_persistence"] == "PASS"
    for required in (
        "`provenance_gate_blocker_persistence` | `PASS`",
        "`b5_status` | `BLOCKED`",
        "`connector_enablement_ready` | `False`",
        "`provenance_reason` | `INDEPENDENT_HUMAN_CONNECTOR_APPROVAL_PROVENANCE_MISSING`",
        "`runtime_loop_started` | `False`",
        "`runtime_order_routing_enabled` | `False`",
        "`campaign_execution` | `False`",
        "`session_execution` | `False`",
        "`run_execution` | `False`",
        "`ledger_mutation` | `False`",
        "`connector_ready_dialects_count` | `1`",
    ):
        assert required in text


def test_phase79h_summary_points_to_next_blocker() -> None:
    text = _normalized_summary_text()

    assert "INDEPENDENT_HUMAN_CONNECTOR_APPROVAL_PROVENANCE_MISSING" in text
    assert "`connector_enablement_ready` | `False`" in text
