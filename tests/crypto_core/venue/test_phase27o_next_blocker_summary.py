"""Phase 27O next blocker summary tests."""

from __future__ import annotations

from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import evaluate_deribit_manual_review_readiness
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

REPO_ROOT = Path(__file__).resolve().parents[3]
SUMMARY = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_NEXT_BLOCKER_SUMMARY_27O.md"


def test_phase27o_summary_records_operational_acceptance_state() -> None:
    text = SUMMARY.read_text(encoding="utf-8")

    assert "status: SOURCE_SNAPSHOT_ACCEPTANCE_COMPLETE" in text
    assert "| `accepted` | `True` |" in text
    assert "| `B1` | `READY_FOR_HUMAN_GATE` |" in text
    assert "| `B2` | `READY` |" in text
    assert "| `connector_ready_dialects_count` | `1` |" in text


def test_phase27o_summary_preserves_public_market_data_boundaries() -> None:
    text = SUMMARY.read_text(encoding="utf-8")

    assert "NOT_private_api: true" in text
    assert "NOT_credentials: true" in text
    assert "NOT_orders: true" in text
    assert "NOT_live_trading: true" in text
    assert "NOT_paper_shadow_execution: true" in text
    assert "NOT_connector_expansion: true" in text


def test_phase27o_live_validator_matches_summary() -> None:
    result = evaluate_deribit_manual_review_readiness()

    assert result.accepted is True
    assert result.b1_b5_status["B1"] == "READY_FOR_HUMAN_GATE"
    assert result.b1_b5_status["B2"] == "READY"
    assert len(connector_ready_dialects()) == 1
