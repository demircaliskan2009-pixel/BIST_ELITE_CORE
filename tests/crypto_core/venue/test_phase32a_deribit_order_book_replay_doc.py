from __future__ import annotations

from pathlib import Path

DOC = Path("docs/crypto_core/DERIBIT_ORDER_BOOK_REPLAY_32A.md")


def test_phase32a_doc_exists_and_records_verified_pr74_state() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert DOC.exists()
    assert "DERIBIT_ORDER_BOOK_REPLAY_READY" in text
    assert "| `accepted` | `True` |" in text
    assert "| `connector_ready_dialects_count` | `1` |" in text
    assert "| `public_feed_ingest_wiring_status` | `READY` |" in text


def test_phase32a_doc_describes_selected_replay_seam_and_scope() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert "crypto_core/data/order_book.py" in text
    assert "deribit_order_book_replay.py" in text
    assert "Snapshot initializes state" in text
    assert "Delta requires an initialized state" in text
    assert "gap tolerance remains `0`" in text
    assert "crossed resulting state" in text.lower()
    assert "No live-network CI dependency" in text or "live-network ci dependency" in text.lower()
    assert "paper feed pipeline" in text.lower()
