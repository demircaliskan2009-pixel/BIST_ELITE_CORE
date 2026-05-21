from __future__ import annotations

from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import evaluate_deribit_manual_review_readiness
from crypto_core.venue.deribit_paper_feed import build_deribit_paper_feed_input
from crypto_core.venue.public_feed_dialects import connector_ready_dialects
from tests.crypto_core.venue.phase33_deribit_paper_feed_helpers import accepted_replay_result

SUMMARY = Path("docs/crypto_core/DERIBIT_NEXT_BLOCKER_SUMMARY_33F.md")


def test_phase33f_summary_records_post_patch_outputs() -> None:
    text = SUMMARY.read_text(encoding="utf-8")
    readiness = evaluate_deribit_manual_review_readiness()
    paper_feed = build_deribit_paper_feed_input(accepted_replay_result())

    assert "| `accepted` | `True` |" in text
    assert "| `evidence_review_complete` | `True` |" in text
    assert "| `connector_enablement_ready` | `True` |" in text
    assert "| `pending_rows` | `0` |" in text
    assert "| `deferred_rows` | `()` |" in text
    assert "| `connector_ready_dialects` | `1` |" in text
    assert "| `paper_feed_input_status` | `READY` |" in text
    assert readiness.accepted is True
    assert len(connector_ready_dialects()) == 1
    assert paper_feed.accepted is True


def test_phase33f_summary_distinguishes_paper_feed_input_from_execution() -> None:
    text = SUMMARY.read_text(encoding="utf-8").lower()

    assert "paper-feed input readiness is not trade readiness" in text
    assert "paper execution" in text
    assert "fill readiness" in text
    assert "order intents" in text
    assert "execution adapters" in text
    assert "fills" in text
    assert "live trading" in text
