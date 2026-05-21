"""Phase 27H public connector enablement result tests."""

from __future__ import annotations

from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import evaluate_deribit_manual_review_readiness
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

REPO_ROOT = Path(__file__).resolve().parents[3]
RESULT = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_PUBLIC_CONNECTOR_ENABLEMENT_RESULT_27H.md"


def test_phase27h_result_records_public_market_data_ready_not_trade_ready() -> None:
    text = RESULT.read_text(encoding="utf-8")

    assert "status: PUBLIC_MARKET_DATA_CONNECTOR_READY" in text
    assert "| `connector_ready_dialects_count` | `1` |" in text
    assert "| `connector_enablement_ready` | `True` |" in text
    assert "| `B5` | `READY` |" in text
    assert "It is not trade-ready" in text
    assert "private API access, credentials" in text
    assert "orders, deposits, withdrawals" in text


def test_phase27h_validator_reflects_phase27k_source_snapshot_acceptance() -> None:
    result = evaluate_deribit_manual_review_readiness()

    assert result.accepted is True
    assert result.evidence_review_complete is True
    assert result.ready_for_engineering_patch is True
    assert result.connector_enablement_ready is True
    assert result.pending_rows == ()
    assert result.deferred_rows == ()
    assert result.b1_b5_status["B1"] == "READY_FOR_HUMAN_GATE"
    assert result.b1_b5_status["B2"] == "READY"
    assert result.b1_b5_status["B3"] == "READY"
    assert result.b1_b5_status["B4"] == "READY"
    assert result.b1_b5_status["B5"] == "READY"
    assert len(connector_ready_dialects()) == 1


def test_phase27h_result_preserves_future_runtime_boundaries() -> None:
    text = RESULT.read_text(encoding="utf-8").lower()
    assert "public feed non-order smoke" in text
    assert "normalized `marketevent` integration" in text
    assert "paper/shadow read-only pipeline" in text
    assert "risk and guardrail gate before any trade" in text
