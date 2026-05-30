from __future__ import annotations

from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import evaluate_deribit_manual_review_readiness
from crypto_core.venue.deribit_marketevent_normalizer import normalize_deribit_public_book_parse_result
from crypto_core.venue.deribit_public_data_quality import evaluate_deribit_normalized_book_quality
from crypto_core.venue.deribit_public_feed_adapter import DERIBIT_PUBLIC_BOOK_CHANNEL, parse_deribit_public_book_payload
from crypto_core.venue.deribit_public_feed_ingest import ingest_deribit_public_data_quality_result
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

SUMMARY = Path("docs/crypto_core/DERIBIT_NEXT_BLOCKER_SUMMARY_31F.md")
EVENT_TIME_NS = 1_700_000_000_000_000_000
RECEIVED_AT_NS = EVENT_TIME_NS + 500_000_000


def test_phase31f_summary_records_post_patch_outputs() -> None:
    text = SUMMARY.read_text(encoding="utf-8")
    readiness = evaluate_deribit_manual_review_readiness()
    ingest = ingest_deribit_public_data_quality_result(
        evaluate_deribit_normalized_book_quality(
            normalize_deribit_public_book_parse_result(
                parse_deribit_public_book_payload(_payload(), received_at_ns=RECEIVED_AT_NS)
            )
        )
    )

    assert "| `accepted` | `True` |" in text
    assert "| `connector_ready_dialects_count` | `1` |" in text
    assert "| `public_feed_ingest_wiring_status` | `READY` |" in text
    assert "| `feed_gate_ready` | `NOT_READY_BY_DESIGN` |" in text
    assert "| `paper_readiness` | `NOT_READY_BY_DESIGN` |" in text
    assert readiness.accepted is True
    assert len(connector_ready_dialects()) == 1
    assert ingest.accepted is True
    assert ingest.ingest_result is not None
    assert ingest.ingest_result.readiness_snapshot.feed_gate_ready is False
    assert ingest.ingest_result.readiness_snapshot.accepted_for_paper is False


def test_phase31f_summary_keeps_next_phase_bounded() -> None:
    text = SUMMARY.read_text(encoding="utf-8")

    assert "still not trade-ready" in text.lower()
    assert "order-book state apply/replay" in text.lower()
    assert "orders" in text.lower()
    assert "live trading" in text.lower()


def _payload() -> dict[str, object]:
    return {
        "method": "subscription",
        "params": {
            "channel": DERIBIT_PUBLIC_BOOK_CHANNEL,
            "data": {
                "type": "snapshot",
                "timestamp": 1_700_000_000_000,
                "instrument_name": "BTC-PERPETUAL",
                "change_id": 101,
                "prev_change_id": 100,
                "bids": [["change", 50_000.0, 1.25]],
                "asks": [["change", 50_010.0, 0.75]],
            },
        },
    }
