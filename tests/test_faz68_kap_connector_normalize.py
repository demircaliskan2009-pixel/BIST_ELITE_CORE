"""
FAZ68: KAP connector v1 — ingest disclosures from fixture HTML/JSON into knowledge documents.
Tests: doc_id sha256, stable fields (source, published_at_utc, title, body, tickers[]), no network.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from bist_core.connectors.kap import (
    SOURCE_KAP,
    ingest_from_html,
    ingest_from_json,
    normalize_to_knowledge_doc,
)


def test_faz68_normalize_to_knowledge_doc_stable_schema() -> None:
    """normalize_to_knowledge_doc returns doc_id (sha256), source, published_at_utc, title, body, tickers[]."""
    doc = normalize_to_knowledge_doc(
        source=SOURCE_KAP,
        published_at_utc="2099-01-01T10:00:00.000Z",
        title="Test Disclosure",
        body="Body text",
        tickers=["ASELS", "THYAO"],
    )
    assert "doc_id" in doc
    assert len(doc["doc_id"]) == 64
    assert all(c in "0123456789abcdef" for c in doc["doc_id"])
    assert doc["source"] == SOURCE_KAP
    assert doc["published_at_utc"] == "2099-01-01T10:00:00.000Z"
    assert doc["title"] == "Test Disclosure"
    assert doc["body"] == "Body text"
    assert doc["tickers"] == ["ASELS", "THYAO"]


def test_faz68_doc_id_deterministic() -> None:
    """Same inputs -> same doc_id (sha256)."""
    doc1 = normalize_to_knowledge_doc(
        source=SOURCE_KAP,
        published_at_utc="2099-01-01T09:00:00.000Z",
        title="Same",
        body="",
        tickers=["X"],
    )
    doc2 = normalize_to_knowledge_doc(
        source=SOURCE_KAP,
        published_at_utc="2099-01-01T09:00:00.000Z",
        title="Same",
        body="",
        tickers=["X"],
    )
    assert doc1["doc_id"] == doc2["doc_id"]
    different = normalize_to_knowledge_doc(
        source=SOURCE_KAP,
        published_at_utc="2099-01-01T09:00:00.000Z",
        title="Other",
        body="",
        tickers=["X"],
    )
    assert doc1["doc_id"] != different["doc_id"]


def test_faz68_ingest_from_html_fixture_no_network() -> None:
    """Ingest from fixture kap_sample.html -> knowledge docs with stable fields."""
    repo_root = Path(__file__).resolve().parents[1]
    fixture = repo_root / "tests" / "fixtures" / "kap_sample.html"
    assert fixture.is_file(), "tests/fixtures/kap_sample.html required"
    docs = ingest_from_html(fixture)
    assert len(docs) == 3
    for doc in docs:
        assert "doc_id" in doc and len(doc["doc_id"]) == 64
        assert doc["source"] == SOURCE_KAP
        assert "published_at_utc" in doc
        assert "title" in doc
        assert "body" in doc
        assert "tickers" in doc and isinstance(doc["tickers"], list)
    titles = [d["title"] for d in docs]
    assert "KAP Notice A" in titles
    assert "KAP Notice B" in titles
    assert "Capital Action" in titles
    tickers = [d["tickers"] for d in docs]
    assert ["ASELS"] in tickers
    assert ["THYAO"] in tickers
    assert ["AKBNK"] in tickers


def test_faz68_ingest_from_html_empty_fixture() -> None:
    """Empty table -> empty list."""
    repo_root = Path(__file__).resolve().parents[1]
    fixture = repo_root / "tests" / "fixtures" / "kap_sample_empty.html"
    assert fixture.is_file()
    docs = ingest_from_html(fixture)
    assert docs == []


def test_faz68_ingest_from_html_string_no_network() -> None:
    """Ingest from HTML string (no file, no network)."""
    html = """
    <table><tbody>
    <tr><td>2099-06-15 14:00</td><td>EKZNC</td><td>KAP</td><td>Test Title</td></tr>
    </tbody></table>
    """
    docs = ingest_from_html(html)
    assert len(docs) == 1
    assert docs[0]["title"] == "Test Title"
    assert docs[0]["tickers"] == ["EKZNC"]
    assert docs[0]["source"] == SOURCE_KAP
    assert "2099-06-15" in docs[0]["published_at_utc"]


def test_faz68_ingest_from_json_fixture_no_network(tmp_path: Path) -> None:
    """Ingest from JSON fixture -> knowledge docs."""
    fixture = tmp_path / "disclosures.json"
    fixture.write_text(
        json.dumps({
            "disclosures": [
                {"ts": "2099-01-01 10:00", "symbol": "ASELS", "title": "Disclosure A", "body": "Content A"},
                {"published_at_utc": "2099-01-01T09:00:00.000Z", "tickers": ["THYAO"], "title": "Disclosure B"},
            ]
        }),
        encoding="utf-8",
    )
    docs = ingest_from_json(fixture)
    assert len(docs) == 2
    assert docs[0]["title"] == "Disclosure A"
    assert docs[0]["tickers"] == ["ASELS"]
    assert docs[0]["body"] == "Content A"
    assert docs[1]["title"] == "Disclosure B"
    assert docs[1]["tickers"] == ["THYAO"]
    for d in docs:
        assert len(d["doc_id"]) == 64 and d["source"] == SOURCE_KAP


def test_faz68_ingest_from_json_list_no_network() -> None:
    """Ingest from JSON list (no file path); doc_id is sha256 of canonical fields."""
    data = [
        {"ts": "2099-02-01 12:00", "symbol": "X", "title": "One"},
    ]
    docs = ingest_from_json(data)
    assert len(docs) == 1
    doc = docs[0]
    assert len(doc["doc_id"]) == 64 and all(c in "0123456789abcdef" for c in doc["doc_id"])
    assert doc["title"] == "One" and doc["tickers"] == ["X"]
    assert doc["doc_id"] == hashlib.sha256(
        "\t".join([SOURCE_KAP, doc["published_at_utc"], "One", "X"]).encode("utf-8")
    ).hexdigest()


def test_faz68_tickers_sorted_deduped() -> None:
    """Tickers are sorted and deduplicated in output."""
    doc = normalize_to_knowledge_doc(
        source=SOURCE_KAP,
        published_at_utc="2099-01-01T00:00:00.000Z",
        title="T",
        body="",
        tickers=["THYAO", "ASELS", "ASELS"],
    )
    assert doc["tickers"] == ["ASELS", "THYAO"]


def test_faz68_research_cache_wired_to_kap_fixture(tmp_path: Path) -> None:
    """Research cache with source=kap and kap_fixture_path uses connector; no network."""
    repo_root = Path(__file__).resolve().parents[1]
    fixture = repo_root / "tests" / "fixtures" / "kap_sample.html"
    assert fixture.is_file()
    from bist_core.research.cache import build_research_cache
    result = build_research_cache(
        "2099-01-20",
        tmp_path,
        source="kap",
        offline=True,
        kap_fixture_path=str(fixture),
    )
    assert result["errors"] == 0
    assert result["count"] == 3
    entries_path = tmp_path / "2099-01-20" / "research" / "entries.jsonl"
    assert entries_path.is_file()
    lines = entries_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3
    first = json.loads(lines[0])
    assert "doc_id" in first or "id" in first
    assert len(first.get("id", first.get("doc_id", ""))) == 64
    assert first.get("title") and first.get("tickers") is not None
