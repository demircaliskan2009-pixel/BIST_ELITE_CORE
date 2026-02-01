"""FAZ91: KAP ingest offline — html -> events.json (hash + source); 0 network, deterministic ids."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from bist_core.events.kap_ingest import ingest_kap_html, write_events_json


FIXTURES_KAP = Path(__file__).resolve().parent / "fixtures" / "kap"


def test_faz91_ingest_from_fixture_no_network(tmp_path: Path) -> None:
    """Ingest uses only local fixture HTML; no network calls."""
    sample = FIXTURES_KAP / "sample.html"
    assert sample.is_file(), "fixture tests/fixtures/kap/sample.html must exist"
    data = ingest_kap_html(sample)
    assert "hash" in data
    assert "source" in data
    assert data["source"] == str(sample)
    assert "events" in data
    assert len(data["events"]) == 3


def test_faz91_deterministic_ids() -> None:
    """Same HTML -> same event ids and same hash (deterministic)."""
    sample = FIXTURES_KAP / "sample.html"
    assert sample.is_file()
    data1 = ingest_kap_html(sample)
    data2 = ingest_kap_html(sample)
    assert data1["hash"] == data2["hash"]
    ids1 = [e["id"] for e in data1["events"]]
    ids2 = [e["id"] for e in data2["events"]]
    assert ids1 == ids2
    assert len(ids1) == len(set(ids1)), "ids must be unique"


def test_faz91_deterministic_ids_from_string() -> None:
    """Same HTML string -> same ids (no file path)."""
    html = (FIXTURES_KAP / "sample.html").read_text(encoding="utf-8")
    data1 = ingest_kap_html(html, source="kap")
    data2 = ingest_kap_html(html, source="kap")
    assert data1["hash"] == data2["hash"]
    assert [e["id"] for e in data1["events"]] == [e["id"] for e in data2["events"]]


def test_faz91_events_json_has_hash_and_source(tmp_path: Path) -> None:
    """write_events_json produces events.json with hash and source."""
    sample = FIXTURES_KAP / "sample.html"
    data = ingest_kap_html(sample)
    out = tmp_path / "events.json"
    write_events_json(out, data)
    assert out.is_file()
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["hash"] == data["hash"]
    assert loaded["source"] == data["source"]
    assert len(loaded["events"]) == len(data["events"])
    for ev in loaded["events"]:
        assert "id" in ev
        assert "symbol" in ev
        assert "ts" in ev
        assert "kind" in ev
        assert "title" in ev


def test_faz91_empty_fixture_produces_no_events() -> None:
    """Empty KAP HTML -> events list empty, hash/source still present."""
    empty = FIXTURES_KAP / "empty.html"
    assert empty.is_file()
    data = ingest_kap_html(empty)
    assert "hash" in data
    assert "source" in data
    assert data["events"] == []
