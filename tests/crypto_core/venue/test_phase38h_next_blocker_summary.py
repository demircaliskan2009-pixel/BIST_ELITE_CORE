from __future__ import annotations

from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import evaluate_deribit_manual_review_readiness
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

SUMMARY = Path("docs/crypto_core/DERIBIT_NEXT_BLOCKER_SUMMARY_38H.md")


def test_phase38h_summary_records_post_patch_outputs() -> None:
    text = SUMMARY.read_text(encoding="utf-8")
    readiness = evaluate_deribit_manual_review_readiness()

    assert "| `accepted` | `True` |" in text
    assert "| `evidence_review_complete` | `True` |" in text
    assert "| `connector_enablement_ready` | `True` |" in text
    assert "| `pending_rows` | `0` |" in text
    assert "| `deferred_rows` | `()` |" in text
    assert "| `connector_ready_dialects` | `1` |" in text
    assert "| `first_paper_trade_smoke_proof_status` | `READY` |" in text
    assert readiness.accepted is True
    assert len(connector_ready_dialects()) == 1


def test_phase38h_summary_keeps_next_phase_bounded() -> None:
    text = SUMMARY.read_text(encoding="utf-8").lower()

    assert "live_ready" in text
    assert "automatic_paper_loop_ready" in text
    assert "production_paper_trading_loop_enabled" in text
    assert "paper trade audit/reporting gate" in text
    assert "operator-triggered paper run harness" in text
    assert "exchange order" in text
    assert "routing" in text
    assert "live trading" in text
    assert "shadow trading" in text
