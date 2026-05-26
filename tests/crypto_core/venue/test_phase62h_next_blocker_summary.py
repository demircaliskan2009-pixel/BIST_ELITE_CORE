from __future__ import annotations

from pathlib import Path

from crypto_core.venue.public_feed_dialects import connector_ready_dialects
from tests.crypto_core.venue.test_phase62b_paper_promoted_runtime_wiring_artifact import _runtime_wiring

SUMMARY = Path("docs/crypto_core/DERIBIT_NEXT_BLOCKER_SUMMARY_62H.md")


def _normalized_summary_text() -> str:
    return " ".join(SUMMARY.read_text(encoding="utf-8").split())


def test_phase62h_next_blocker_summary_records_current_readiness_state() -> None:
    text = SUMMARY.read_text(encoding="utf-8")

    assert len(connector_ready_dialects()) == 1
    assert "`accepted` | `True`" in text
    assert "`pending_rows` | `0`" in text
    assert "`deferred_rows` | `()`" in text
    assert "`connector_ready_dialects` | `1`" in text
    assert "`B1` | `READY_FOR_HUMAN_GATE`" in text
    for field in ("`B2` | `READY`", "`B3` | `READY`", "`B4` | `READY`", "`B5` | `READY`"):
        assert field in text


def test_phase62h_next_blocker_summary_records_runtime_wiring_state() -> None:
    text = _normalized_summary_text()
    artifact = _runtime_wiring()

    assert artifact["runtime_wiring_status"] == "WIRED"
    for required in (
        "`runtime_readiness_verdict` | `PASS`",
        "`runtime_wiring_status` | `WIRED`",
        "`ready_for_paper_runtime` | `True`",
        "`runtime_enabled` | `False`",
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


def test_phase62h_next_blocker_summary_points_to_enablement_approval_gate() -> None:
    text = _normalized_summary_text()

    assert "PAPER_PROMOTED_RUNTIME_ENABLEMENT_APPROVAL_NOT_READY" in text
    assert "explicit operator approval" in text
