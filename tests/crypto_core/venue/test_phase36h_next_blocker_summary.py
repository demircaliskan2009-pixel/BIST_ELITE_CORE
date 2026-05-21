from __future__ import annotations

from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import evaluate_deribit_manual_review_readiness
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

SUMMARY = Path("docs/crypto_core/DERIBIT_NEXT_BLOCKER_SUMMARY_36H.md")


def test_phase36h_summary_records_post_patch_outputs() -> None:
    text = SUMMARY.read_text(encoding="utf-8")
    readiness = evaluate_deribit_manual_review_readiness()

    assert "| `accepted` | `True` |" in text
    assert "| `evidence_review_complete` | `True` |" in text
    assert "| `connector_enablement_ready` | `True` |" in text
    assert "| `pending_rows` | `0` |" in text
    assert "| `deferred_rows` | `()` |" in text
    assert "| `connector_ready_dialects` | `1` |" in text
    assert "| `paper_ledger_fill_application_status` | `READY` |" in text
    assert readiness.accepted is True
    assert len(connector_ready_dialects()) == 1


def test_phase36h_summary_keeps_next_phase_bounded() -> None:
    text = SUMMARY.read_text(encoding="utf-8").lower()

    assert "paper ledger readiness does not equal automatic paper trading loop readiness" in text
    assert "live orders" in text
    assert "execution adapters" in text
    assert "shadow or live" in text
    assert "trading out of scope" in text
    assert "paper-trade gate or orchestrator" in text
