from __future__ import annotations

from pathlib import Path

from crypto_core.venue.public_feed_dialects import connector_ready_dialects, get_public_feed_dialect

MODULE = Path("src/crypto_core/venue/deribit_order_book_replay.py")
DOC = Path("docs/crypto_core/DERIBIT_ORDER_BOOK_REPLAY_32A.md")
SUMMARY = Path("docs/crypto_core/DERIBIT_NEXT_BLOCKER_SUMMARY_32F.md")


def test_phase32e_module_stays_offline_non_trading_and_without_bist_leakage() -> None:
    text = MODULE.read_text(encoding="utf-8").lower()

    assert "requests" not in text
    assert "websocket" not in text
    assert "httpx" not in text
    assert "aiohttp" not in text
    assert "crypto_core.execution" not in text
    assert "crypto_core.paper" not in text
    assert "crypto_core.shadow" not in text
    assert "crypto_core.bist" not in text
    assert "async def" not in text
    assert "wss://" not in text
    assert "https://" not in text


def test_phase32e_docs_keep_scope_bounded_and_public_feed_dialect_policy_unchanged() -> None:
    doc_text = DOC.read_text(encoding="utf-8")
    summary_text = SUMMARY.read_text(encoding="utf-8")
    spec = get_public_feed_dialect("deribit:l2_orderbook:book_instrument_interval")

    assert "NOT_private_api: true" in doc_text
    assert "NOT_credentials: true" in doc_text
    assert "NOT_orders: true" in doc_text
    assert "NOT_live_trading: true" in doc_text
    assert "still not trade-ready" in summary_text.lower()
    assert "paper feed pipeline" in summary_text.lower()
    assert len(connector_ready_dialects()) == 1
    assert spec.max_gap_tolerance == 0
    assert spec.max_staleness_ns == 2_000_000_000
    assert spec.max_receive_lag_ns == 1_000_000_000
