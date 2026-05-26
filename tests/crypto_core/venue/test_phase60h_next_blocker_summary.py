from __future__ import annotations

from pathlib import Path

from crypto_core.venue.public_feed_dialects import connector_ready_dialects
from tests.crypto_core.venue.test_phase60b_paper_promotion_post_audit_artifact import _post_audit

SUMMARY = Path("docs/crypto_core/DERIBIT_NEXT_BLOCKER_SUMMARY_60H.md")


def _normalized_summary_text() -> str:
    return " ".join(SUMMARY.read_text(encoding="utf-8").split())


def test_phase60h_next_blocker_summary_records_current_readiness_state() -> None:
    text = SUMMARY.read_text(encoding="utf-8")

    assert len(connector_ready_dialects()) == 1
    assert "`accepted` | `True`" in text
    assert "`pending_rows` | `0`" in text
    assert "`deferred_rows` | `()`" in text
    assert "`connector_ready_dialects` | `1`" in text
    assert "`B1` | `READY_FOR_HUMAN_GATE`" in text
    for field in ("`B2` | `READY`", "`B3` | `READY`", "`B4` | `READY`", "`B5` | `READY`"):
        assert field in text


def test_phase60h_next_blocker_summary_records_post_audit_state() -> None:
    text = _normalized_summary_text()
    artifact = _post_audit()

    assert artifact["post_audit_status"] == "POST_AUDITED"
    for required in (
        "`post_audit_status` | `POST_AUDITED`",
        "`post_audit_verdict` | `PASS`",
        "`promotion_telemetry_audit_verdict` | `PASS`",
        "`promotion_granted` | `True`",
        "`paper_promoted` | `True`",
        "`live_ready` | `False`",
        "`shadow_ready` | `False`",
        "`campaign_execution` | `False`",
        "`ledger_mutation` | `False`",
        "`automatic_paper_loop_ready` | `NO`",
        "`scheduler_ready` | `NO`",
    ):
        assert required in text


def test_phase60h_next_blocker_summary_points_to_runtime_readiness_gate() -> None:
    text = _normalized_summary_text()

    assert "PAPER_PROMOTED_RUNTIME_READINESS_NOT_READY" in text
    assert "no-new-execution boundary" in text
