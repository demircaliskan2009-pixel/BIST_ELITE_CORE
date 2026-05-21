from __future__ import annotations

from pathlib import Path

MODULE = Path("src/crypto_core/venue/deribit_public_feed_ingest.py")
DOC = Path("docs/crypto_core/DERIBIT_PUBLIC_FEED_INGEST_WIRING_31A.md")
SUMMARY = Path("docs/crypto_core/DERIBIT_NEXT_BLOCKER_SUMMARY_31F.md")


def test_phase31e_module_stays_offline_and_non_trading() -> None:
    text = MODULE.read_text(encoding="utf-8").lower()

    assert "requests" not in text
    assert "websocket" not in text
    assert "ccxt" not in text
    assert "crypto_core.execution" not in text
    assert "crypto_core.paper" not in text
    assert "crypto_core.shadow" not in text
    assert "async def" not in text
    assert "wss://" not in text
    assert "https://" not in text


def test_phase31e_docs_keep_non_trading_scope_explicit() -> None:
    doc_text = DOC.read_text(encoding="utf-8")
    summary_text = SUMMARY.read_text(encoding="utf-8")

    assert "NOT_private_api: true" in doc_text
    assert "NOT_credentials: true" in doc_text
    assert "NOT_orders: true" in doc_text
    assert "NOT_live_trading: true" in doc_text
    assert "still not trade-ready" in summary_text.lower()
    assert "order-book state apply/replay" in summary_text.lower()
