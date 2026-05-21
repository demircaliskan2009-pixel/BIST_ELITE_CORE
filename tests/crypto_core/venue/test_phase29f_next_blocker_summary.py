from __future__ import annotations

from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import evaluate_deribit_manual_review_readiness
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

SUMMARY = Path("docs/crypto_core/DERIBIT_NEXT_BLOCKER_SUMMARY_29F.md")


def test_phase29f_summary_records_post_patch_outputs() -> None:
    text = SUMMARY.read_text(encoding="utf-8")
    result = evaluate_deribit_manual_review_readiness()

    assert "| `accepted` | `True` |" in text
    assert "| `connector_enablement_ready` | `True` |" in text
    assert "| `pending_rows` | `0` |" in text
    assert "| `deferred_rows` | `()` |" in text
    assert "| `connector_ready_dialects_count` | `1` |" in text
    assert result.accepted is True
    assert len(connector_ready_dialects()) == 1


def test_phase29f_summary_distinguishes_normalization_from_trade_readiness() -> None:
    text = SUMMARY.read_text(encoding="utf-8")

    assert "PUBLIC_BOOK_MARKETEVENT_NORMALIZATION_READY" in text
    assert "canonical_public_market_data_event" in text
    assert "type_less_aggregated_book_mapping" in text
    assert "NOT_private_api: true" in text
    assert "NOT_credentials: true" in text
    assert "NOT_orders: true" in text
    assert "NOT_live_trading: true" in text
    assert "data-quality runtime gate" in text
