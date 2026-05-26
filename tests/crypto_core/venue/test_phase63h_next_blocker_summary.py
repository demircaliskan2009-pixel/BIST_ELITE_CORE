from __future__ import annotations

from pathlib import Path

from crypto_core.venue.public_feed_dialects import connector_ready_dialects
from tests.crypto_core.venue.test_phase63b_runtime_enablement_proposal_artifact import _proposal

SUMMARY = Path("docs/crypto_core/DERIBIT_NEXT_BLOCKER_SUMMARY_63H.md")


def _normalized_summary_text() -> str:
    return " ".join(SUMMARY.read_text(encoding="utf-8").split())


def test_phase63h_next_blocker_summary_records_current_readiness_state() -> None:
    text = SUMMARY.read_text(encoding="utf-8")

    assert len(connector_ready_dialects()) == 1
    assert "`accepted` | `True`" in text
    assert "`pending_rows` | `0`" in text
    assert "`deferred_rows` | `()`" in text
    assert "`connector_ready_dialects` | `1`" in text
    assert "`B1` | `READY_FOR_HUMAN_GATE`" in text
    for field in ("`B2` | `READY`", "`B3` | `READY`", "`B4` | `READY`", "`B5` | `READY`"):
        assert field in text


def test_phase63h_next_blocker_summary_records_proposal_without_runtime_enablement() -> None:
    text = _normalized_summary_text()
    proposal = _proposal()

    assert proposal["proposal_status"] == "READY_FOR_OPERATOR_REVIEW"
    for required in (
        "`runtime_wiring_status` | `WIRED`",
        "`proposal_status` | `READY_FOR_OPERATOR_REVIEW`",
        "`approval_status` | `NOT_APPROVED`",
        "`operator_metadata_required` | `True`",
        "`runtime_enablement_approved` | `False`",
        "`runtime_enabled` | `False`",
        "`runtime_started` | `False`",
        "`paper_promoted` | `True`",
        "`promotion_granted` | `True`",
        "`promotion_scope` | `PAPER_ONLY_SIMULATION_ONLY`",
        "`live_ready` | `False`",
        "`shadow_ready` | `False`",
        "`campaign_execution` | `False`",
        "`ledger_mutation` | `False`",
    ):
        assert required in text


def test_phase63h_next_blocker_summary_points_to_approval_metadata_gate() -> None:
    text = _normalized_summary_text()

    assert "OPERATOR_PAPER_RUNTIME_ENABLEMENT_APPROVAL_NOT_READY" in text
    assert "runtime must remain disabled and not started" in text
