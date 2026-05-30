from __future__ import annotations

from pathlib import Path

from crypto_core.data.public_feed_dialect import FeedChecksumModel, FeedSequenceModel
from crypto_core.venue.deribit_paper_feed import build_deribit_paper_feed_input
from crypto_core.venue.deribit_paper_fill_model import (
    DeribitPaperFillRequest,
    DeribitPaperFillSide,
    DeribitPaperFillStyle,
    evaluate_deribit_paper_limit_fill,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects
from tests.crypto_core.venue.phase33_deribit_paper_feed_helpers import accepted_replay_result

REGISTRY = Path("src/crypto_core/venue/public_feed_dialects.py")


def test_phase34e_connector_ready_dialect_count_and_policy_values_preserved() -> None:
    ready = connector_ready_dialects()
    result = evaluate_deribit_paper_limit_fill(_frame(), _request())

    assert result.accepted is True
    assert len(ready) == 1
    spec = ready[0]
    assert spec.dialect_id == "deribit:l2_orderbook:book_instrument_interval"
    assert spec.supports_checksum is False
    assert spec.checksum_model is FeedChecksumModel.NONE
    assert spec.sequence_model is FeedSequenceModel.SNAPSHOT_DELTA_RANGE
    assert spec.max_gap_tolerance == 0
    assert spec.max_staleness_ns == 2_000_000_000
    assert spec.max_receive_lag_ns == 1_000_000_000


def test_phase34e_public_feed_registry_was_not_mutated_for_phase34() -> None:
    registry_text = REGISTRY.read_text(encoding="utf-8")

    assert "DERIBIT_PAPER_FILL_MODEL_ID" not in registry_text
    assert "phase34" not in registry_text.lower()


def _frame():
    paper_feed = build_deribit_paper_feed_input(accepted_replay_result())
    assert paper_feed.frame is not None
    return paper_feed.frame


def _request() -> DeribitPaperFillRequest:
    return DeribitPaperFillRequest(
        request_id="sim-req-policy",
        side=DeribitPaperFillSide.BUY,
        style=DeribitPaperFillStyle.LIMIT,
        quantity=0.5,
        limit_price=50_020.0,
        simulation_only=True,
    )
