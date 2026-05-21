from __future__ import annotations

from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import evaluate_deribit_manual_review_readiness
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

REPO_ROOT = Path(__file__).resolve().parents[3]
DOC = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_MARKETEVENT_NORMALIZATION_29A.md"


def test_phase29a_current_readiness_preconditions_hold() -> None:
    result = evaluate_deribit_manual_review_readiness()
    ready = connector_ready_dialects()

    assert result.accepted is True
    assert result.connector_enablement_ready is True
    assert result.pending_rows == ()
    assert result.deferred_rows == ()
    assert result.b1_b5_status["B1"] == "READY_FOR_HUMAN_GATE"
    assert all(result.b1_b5_status[gate] == "READY" for gate in ("B2", "B3", "B4", "B5"))
    assert len(ready) == 1
    assert ready[0].dialect_id == "deribit:l2_orderbook:book_instrument_interval"


def test_phase29a_doc_records_canonical_public_marketevent_mapping() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert "status: PUBLIC_BOOK_MARKETEVENT_NORMALIZATION_READY" in text
    assert "crypto_core.venue.contracts.PublicMarketDataEvent" in text
    assert "OrderBookSnapshot" in text
    assert "OrderBookDelta" in text
    assert "`change_id` | `PublicMarketDataEvent.sequence_id` |" in text
    assert "does not invent" in text
    assert "snapshot/delta" in text
    assert "NOT_ci_live_network_dependency: true" in text
