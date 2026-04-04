"""FAZ390: KAP ingestion fixture minimal — parse without network, deterministic event IDs."""

from __future__ import annotations

from pathlib import Path

import pytest

from bist_core.events.kap_ingest import ingest_kap_html


FIXTURES_KAP = Path(__file__).resolve().parent / "fixtures" / "kap"


def test_faz390_kap_minimal_fixture_parses() -> None:
    """Parse tests/fixtures/kap/minimal.html; extract one event; no network."""
    minimal = FIXTURES_KAP / "minimal.html"
    assert minimal.is_file(), "fixture tests/fixtures/kap/minimal.html must exist"
    data = ingest_kap_html(minimal)
    assert "hash" in data
    assert "source" in data
    assert "events" in data
    assert len(data["events"]) == 1
    ev = data["events"][0]
    assert ev["symbol"] == "ASELS"
    assert ev["kind"] == "KAP"
    assert "Minimal Notice" in ev["title"]
    assert "id" in ev
    assert len(ev["id"]) == 64
    assert all(c in "0123456789abcdef" for c in ev["id"])


def test_faz390_kap_minimal_deterministic_event_ids() -> None:
    """Same minimal HTML -> same event id across runs."""
    minimal = FIXTURES_KAP / "minimal.html"
    data1 = ingest_kap_html(minimal)
    data2 = ingest_kap_html(minimal)
    assert data1["hash"] == data2["hash"]
    assert [e["id"] for e in data1["events"]] == [e["id"] for e in data2["events"]]


def test_faz390_kap_empty_html_no_crash() -> None:
    """Empty HTML -> empty events list; no exception."""
    empty = FIXTURES_KAP / "empty.html"
    assert empty.is_file()
    data = ingest_kap_html(empty)
    assert data["events"] == []
    assert "hash" in data
    assert "source" in data


def test_faz390_kap_broken_markup_graceful() -> None:
    """Broken/incomplete markup -> parse what we can; no crash."""
    broken = FIXTURES_KAP / "broken_markup.html"
    if not broken.is_file():
        pytest.skip("broken_markup.html fixture not present")
    data = ingest_kap_html(broken)
    assert "events" in data
    assert "hash" in data
    assert isinstance(data["events"], list)
