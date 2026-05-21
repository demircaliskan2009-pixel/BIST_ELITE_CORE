from __future__ import annotations

from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import evaluate_deribit_manual_review_readiness
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

REPO_ROOT = Path(__file__).resolve().parents[3]
SUMMARY = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_NEXT_BLOCKER_SUMMARY_28F.md"


def test_phase28f_summary_records_post_patch_validator_and_connector_outputs() -> None:
    text = SUMMARY.read_text(encoding="utf-8")
    result = evaluate_deribit_manual_review_readiness()

    assert "| `accepted` | `True` |" in text
    assert "| `connector_enablement_ready` | `True` |" in text
    assert "| `pending_rows` | `0` |" in text
    assert "| `deferred_rows` | `()` |" in text
    assert "| `connector_ready_dialects_count` | `1` |" in text
    assert result.accepted is True
    assert len(connector_ready_dialects()) == 1


def test_phase28f_summary_keeps_trade_readiness_out_of_scope() -> None:
    text = SUMMARY.read_text(encoding="utf-8")

    assert "NOT_private_api: true" in text
    assert "NOT_credentials: true" in text
    assert "NOT_orders: true" in text
    assert "NOT_live_trading: true" in text
    assert "NOT_ci_live_network_dependency: true" in text
    assert "normalized `MarketEvent` integration" in text
    assert "It does not authorize" in text
