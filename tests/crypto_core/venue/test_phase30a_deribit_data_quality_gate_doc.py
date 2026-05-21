from __future__ import annotations

from pathlib import Path

DOC = Path("docs/crypto_core/DERIBIT_DATA_QUALITY_GATE_30A.md")


def test_phase30a_doc_exists_and_records_verified_pr72_state() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert DOC.exists()
    assert "DERIBIT_NORMALIZED_PUBLIC_DATA_QUALITY_GATE_READY" in text
    assert "| `accepted` | `True` |" in text
    assert "| `connector_ready_dialects_count` | `1` |" in text
    assert "| `B1` | `READY_FOR_HUMAN_GATE` |" in text


def test_phase30a_doc_describes_gate_scope_and_policy() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert "PublicMarketDataEvent" in text
    assert "OrderBookSnapshot" in text
    assert "OrderBookDelta" in text
    assert "staleness_ns <= 2_000_000_000" in text
    assert "receive_lag_ns <= 1_000_000_000" in text
    assert "max_gap_tolerance == 0" in text
    assert "checksum remains unsupported/False" in text
    assert "fail-closed" in text
    assert "No live-network CI dependency" in text or "No live-network CI dependency".lower() in text.lower()
    assert "public feed ingest wiring" in text
