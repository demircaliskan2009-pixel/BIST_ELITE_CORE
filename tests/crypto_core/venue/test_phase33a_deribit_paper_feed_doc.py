from __future__ import annotations

from pathlib import Path

DOC = Path("docs/crypto_core/DERIBIT_PAPER_FEED_PIPELINE_33A.md")


def test_phase33a_doc_records_verified_replay_state_and_boundary() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert "DERIBIT_PAPER_FEED_INPUT_READY" in text
    assert "| `main` | `ef684f61a9e9d5b2143a2a412abedbc712ecc6bb` |" in text
    assert "| `connector_ready_dialects` | `1` |" in text
    assert "Order-book replay accepts and produces `OrderBookState`" in text
    assert "replayed public order-book state" in text


def test_phase33a_doc_keeps_execution_and_live_scope_out() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert "NOT_private_api: true" in text
    assert "NOT_credentials: true" in text
    assert "NOT_orders: true" in text
    assert "NOT_order_intents: true" in text
    assert "NOT_execution_adapter: true" in text
    assert "NOT_fills: true" in text
    assert "NOT_shadow_live_trading: true" in text
    assert "BIST" not in text
