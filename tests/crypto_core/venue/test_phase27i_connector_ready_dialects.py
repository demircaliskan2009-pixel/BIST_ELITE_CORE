"""Phase 27I connector-ready dialect regression tests."""

from __future__ import annotations

from pathlib import Path

from crypto_core.venue.contracts import VenueId
from crypto_core.venue.public_feed_dialects import all_public_feed_dialects, connector_ready_dialects

REPO_ROOT = Path(__file__).resolve().parents[3]
SUMMARY = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_NEXT_BLOCKER_SUMMARY_27J.md"


def test_phase27i_connector_ready_dialects_contains_only_deribit_public_market_data() -> None:
    ready = connector_ready_dialects()
    all_specs = all_public_feed_dialects()

    assert len(ready) == 1
    assert ready[0].venue_id is VenueId.DERIBIT
    assert ready[0].enabled_for_connector is True
    assert all(spec.venue_id is VenueId.DERIBIT or spec.enabled_for_connector is False for spec in all_specs)


def test_phase27i_next_summary_distinguishes_connector_and_trade_readiness() -> None:
    text = SUMMARY.read_text(encoding="utf-8")

    assert "| `public_market_data_connector_readiness` | `ACHIEVED` |" in text
    assert "| Private API | `NOT_AUTHORIZED` |" in text
    assert "| Credentials | `NOT_AUTHORIZED` |" in text
    assert "| Orders | `NOT_AUTHORIZED` |" in text
    assert "| Live trading | `NOT_AUTHORIZED` |" in text
    assert "| `B5` | `READY` |" in text


def test_phase27i_next_summary_lists_remaining_safe_engineering_phases() -> None:
    text = SUMMARY.read_text(encoding="utf-8")

    assert "Public feed runtime smoke or adapter readiness" in text
    assert "Normalized `MarketEvent` integration" in text
    assert "Paper/shadow read-only pipeline with no orders" in text
    assert "Risk and guardrail gate before any trade-related capability" in text
    assert "No live orders are authorized" in text
