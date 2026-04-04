"""FAZ391: KAP event dedupe by id — first-wins, deterministic."""

from __future__ import annotations

from pathlib import Path

from bist_core.events.kap_ingest import ingest_kap_html


FIXTURES_KAP = Path(__file__).resolve().parent / "fixtures" / "kap"


def test_faz391_kap_dedupe_by_id() -> None:
    """Duplicate event id (same symbol, ts, kind, title) -> first wins, one event."""
    dup = FIXTURES_KAP / "duplicate_id.html"
    assert dup.is_file()
    data = ingest_kap_html(dup)
    assert len(data["events"]) == 1
    ev = data["events"][0]
    assert ev["symbol"] == "THYAO"
    assert ev["title"] == "First"
    assert ev.get("url") == "/a"


def test_faz391_kap_dedupe_deterministic() -> None:
    """Same input with duplicates -> same output across runs."""
    dup = FIXTURES_KAP / "duplicate_id.html"
    data1 = ingest_kap_html(dup)
    data2 = ingest_kap_html(dup)
    assert data1["hash"] == data2["hash"]
    assert [e["id"] for e in data1["events"]] == [e["id"] for e in data2["events"]]
    assert len(data1["events"]) == len(data2["events"]) == 1
