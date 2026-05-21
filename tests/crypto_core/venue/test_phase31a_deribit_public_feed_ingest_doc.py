from __future__ import annotations

from pathlib import Path

DOC = Path("docs/crypto_core/DERIBIT_PUBLIC_FEED_INGEST_WIRING_31A.md")


def test_phase31a_doc_exists_and_records_verified_baseline() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert DOC.exists()
    assert "DERIBIT_PUBLIC_FEED_INGEST_WIRING_READY" in text
    assert "| `accepted` | `True` |" in text
    assert "| `connector_ready_dialects_count` | `1` |" in text
    assert "| `data_quality_gate_status` | `READY` |" in text


def test_phase31a_doc_describes_reused_ingest_boundary() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert "public_feed_ingest.py" in text
    assert "DeribitPublicDataQualityResult" in text
    assert "PublicFeedBatch" in text
    assert "RawPublicFeedEnvelope" in text
    assert "require_public_data_ready=False" in text
    assert "require_order_book=True" in text
    assert "accepted_for_paper" in text
    assert "fail closed" in text.lower()
