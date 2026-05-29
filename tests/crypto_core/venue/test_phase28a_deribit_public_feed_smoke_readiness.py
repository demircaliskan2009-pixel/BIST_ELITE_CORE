from __future__ import annotations

from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import evaluate_deribit_manual_review_readiness
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

REPO_ROOT = Path(__file__).resolve().parents[3]
DOC = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_PUBLIC_FEED_SMOKE_READINESS_28A.md"


def test_phase28a_current_readiness_preconditions_hold() -> None:
    result = evaluate_deribit_manual_review_readiness()
    ready = connector_ready_dialects()

    assert result.accepted is True
    assert result.evidence_review_complete is True
    assert result.connector_enablement_ready is False
    assert result.pending_rows == ()
    assert result.deferred_rows == ()
    assert result.b1_b5_status == {
        "B1": "READY_FOR_HUMAN_GATE",
        "B2": "READY",
        "B3": "READY",
        "B4": "READY",
        "B5": "BLOCKED",
    }
    assert len(ready) == 1
    assert ready[0].dialect_id == "deribit:l2_orderbook:book_instrument_interval"


def test_phase28a_readiness_doc_records_public_only_ci_offline_scope() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert "status: PUBLIC_FEED_NON_ORDER_SMOKE_READY" in text
    assert "NOT_private_api: true" in text
    assert "NOT_credentials: true" in text
    assert "NOT_orders: true" in text
    assert "NOT_live_trading: true" in text
    assert "NOT_ci_live_network_dependency: true" in text
    assert "Unit tests use sample payloads and do not connect to Deribit." in text
