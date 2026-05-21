from __future__ import annotations

from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import evaluate_deribit_manual_review_readiness
from crypto_core.venue.deribit_paper_feed import build_deribit_paper_feed_input
from crypto_core.venue.deribit_paper_fill_model import (
    DeribitPaperFillRequest,
    DeribitPaperFillSide,
    DeribitPaperFillStyle,
    evaluate_deribit_paper_limit_fill,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects
from tests.crypto_core.venue.phase33_deribit_paper_feed_helpers import accepted_replay_result

SUMMARY = Path("docs/crypto_core/DERIBIT_NEXT_BLOCKER_SUMMARY_34F.md")


def test_phase34f_summary_records_post_patch_outputs() -> None:
    text = SUMMARY.read_text(encoding="utf-8")
    readiness = evaluate_deribit_manual_review_readiness()
    fill = evaluate_deribit_paper_limit_fill(_frame(), _request())

    assert "| `accepted` | `True` |" in text
    assert "| `evidence_review_complete` | `True` |" in text
    assert "| `connector_enablement_ready` | `True` |" in text
    assert "| `pending_rows` | `0` |" in text
    assert "| `deferred_rows` | `()` |" in text
    assert "| `connector_ready_dialects` | `1` |" in text
    assert "| `paper_fill_model_contract_status` | `READY` |" in text
    assert readiness.accepted is True
    assert len(connector_ready_dialects()) == 1
    assert fill.accepted is True


def test_phase34f_summary_distinguishes_contract_from_paper_trading_loop() -> None:
    text = SUMMARY.read_text(encoding="utf-8").lower()

    assert "fill model contract readiness is not automatic paper trading readiness" in text
    assert "not trade readiness" in text
    assert "venue_submission_ready" in text
    assert "trade_ready" in text
    assert "risk, kill-switch" in text
    assert "accounting gates" in text
    assert "live/private exchange" in text


def _frame():
    paper_feed = build_deribit_paper_feed_input(accepted_replay_result())
    assert paper_feed.frame is not None
    return paper_feed.frame


def _request() -> DeribitPaperFillRequest:
    return DeribitPaperFillRequest(
        request_id="sim-req-summary",
        side=DeribitPaperFillSide.BUY,
        style=DeribitPaperFillStyle.LIMIT,
        quantity=0.5,
        limit_price=50_020.0,
        simulation_only=True,
    )
