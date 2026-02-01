"""FAZ92: Doc ingest contract — same content -> same doc_id; store by sha256 key."""
from __future__ import annotations

from pathlib import Path

import pytest

from bist_core.memory.doc_ingest import doc_id_from_content, ingest_doc
from bist_core.memory.store import get_doc, put_doc


FIXTURES_DOCS = Path(__file__).resolve().parent / "fixtures" / "docs"


def test_faz92_same_content_same_doc_id() -> None:
    """Same content (str or bytes) -> same doc_id."""
    text = "KAP disclosure: ASELS dividend decision 2025-01-15.\n"
    id1 = doc_id_from_content(text)
    id2 = doc_id_from_content(text.encode("utf-8"))
    assert id1 == id2
    assert len(id1) == 64
    assert id1 == doc_id_from_content(text)


def test_faz92_ingest_doc_same_content_same_doc_id() -> None:
    """ingest_doc: same content -> same doc_id in returned doc."""
    text = "Capital increase notice THYAO effective 2025-02-01.\n"
    doc1 = ingest_doc(text)
    doc2 = ingest_doc(text.encode("utf-8"))
    assert doc1["doc_id"] == doc2["doc_id"]
    assert doc1["content"] == doc2["content"]
    assert doc1["doc_id"] == doc_id_from_content(text)


def test_faz92_fixture_same_content_same_doc_id() -> None:
    """Fixture docs: note_a and duplicate have same content -> same doc_id."""
    note_a = FIXTURES_DOCS / "note_a.txt"
    duplicate = FIXTURES_DOCS / "duplicate.txt"
    assert note_a.is_file() and duplicate.is_file()
    doc_a = ingest_doc(note_a)
    doc_dup = ingest_doc(duplicate)
    assert doc_a["doc_id"] == doc_dup["doc_id"], "same content must yield same doc_id"
    assert doc_a["content"] == doc_dup["content"]


def test_faz92_fixture_different_content_different_doc_id() -> None:
    """Fixture docs: note_a and note_b different -> different doc_id."""
    doc_a = ingest_doc(FIXTURES_DOCS / "note_a.txt")
    doc_b = ingest_doc(FIXTURES_DOCS / "note_b.txt")
    assert doc_a["doc_id"] != doc_b["doc_id"]


def test_faz92_store_put_get_roundtrip(tmp_path: Path) -> None:
    """put_doc then get_doc by doc_id returns same bytes."""
    content = b"test doc content"
    doc_id = doc_id_from_content(content)
    put_doc(tmp_path, doc_id, content)
    out = get_doc(tmp_path, doc_id)
    assert out == content


def test_faz92_store_ingest_then_get(tmp_path: Path) -> None:
    """ingest_doc from fixture -> put_doc -> get_doc returns same content."""
    path = FIXTURES_DOCS / "note_a.txt"
    doc = ingest_doc(path)
    put_doc(tmp_path, doc["doc_id"], doc["content"])
    retrieved = get_doc(tmp_path, doc["doc_id"])
    assert retrieved == doc["content"]
    assert retrieved == path.read_bytes()
