from __future__ import annotations

from pathlib import Path

MODULE = Path("src/crypto_core/venue/deribit_public_data_quality.py")
DOC = Path("docs/crypto_core/DERIBIT_DATA_QUALITY_GATE_30A.md")
SUMMARY = Path("docs/crypto_core/DERIBIT_NEXT_BLOCKER_SUMMARY_30F.md")


def test_phase30e_module_stays_offline_and_non_trading() -> None:
    text = MODULE.read_text(encoding="utf-8").lower()

    assert "requests" not in text
    assert "websocket" not in text
    assert "ccxt" not in text
    assert "crypto_core.bist" not in text
    assert "crypto_core.execution" not in text
    assert "crypto_core.paper" not in text
    assert "crypto_core.shadow" not in text
    assert "async def" not in text
    assert "wss://" not in text
    assert "https://" not in text


def test_phase30e_docs_keep_non_trading_scope_explicit() -> None:
    doc_text = DOC.read_text(encoding="utf-8")
    summary_text = SUMMARY.read_text(encoding="utf-8")

    assert "NOT_private_api: true" in doc_text
    assert "NOT_credentials: true" in doc_text
    assert "NOT_orders: true" in doc_text
    assert "NOT_live_trading: true" in doc_text
    assert "still not trade-ready" in summary_text.lower()
    assert "public feed ingest behind this quality gate" in summary_text.lower()
