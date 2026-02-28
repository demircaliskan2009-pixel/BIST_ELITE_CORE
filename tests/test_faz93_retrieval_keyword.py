"""FAZ93: Keyword retrieval — build_index(docs) -> search(query, k); deterministic scoring."""

from __future__ import annotations

from pathlib import Path


from bist_core.memory.doc_ingest import ingest_doc
from bist_core.memory.retrieval import build_index


FIXTURES_DOCS = Path(__file__).resolve().parent / "fixtures" / "docs"


def test_faz93_build_index_search_keyword() -> None:
    """build_index from fixture docs; search returns top-k by keyword."""
    docs = [
        ingest_doc(FIXTURES_DOCS / "note_a.txt"),
        ingest_doc(FIXTURES_DOCS / "note_b.txt"),
    ]
    index = build_index(docs)
    results = index.search("ASELS", 5)
    assert len(results) >= 1
    # note_a contains "ASELS"; note_b contains "THYAO"
    asels_doc_id = ingest_doc(FIXTURES_DOCS / "note_a.txt")["doc_id"]
    assert results[0][0] == asels_doc_id
    assert results[0][1] > 0

    results_thyao = index.search("THYAO", 5)
    assert len(results_thyao) >= 1
    thyao_doc_id = ingest_doc(FIXTURES_DOCS / "note_b.txt")["doc_id"]
    assert results_thyao[0][0] == thyao_doc_id


def test_faz93_deterministic_scoring() -> None:
    """Same docs + same query -> same scores and order."""
    docs = [
        ingest_doc(FIXTURES_DOCS / "note_a.txt"),
        ingest_doc(FIXTURES_DOCS / "note_b.txt"),
    ]
    index = build_index(docs)
    r1 = index.search("disclosure", 10)
    r2 = index.search("disclosure", 10)
    assert r1 == r2
    assert all(isinstance(score, float) for _, score in r1)
    # Tie-break by doc_id: stable order
    for i in range(len(r1) - 1):
        if r1[i][1] == r1[i + 1][1]:
            assert r1[i][0] < r1[i + 1][0]


def test_faz93_search_k_limits_results() -> None:
    """search(query, k) returns at most k results."""
    docs = [
        ingest_doc(FIXTURES_DOCS / "note_a.txt"),
        ingest_doc(FIXTURES_DOCS / "note_b.txt"),
    ]
    index = build_index(docs)
    results = index.search("kap disclosure capital", 1)
    assert len(results) <= 1
    results_2 = index.search("kap disclosure capital", 2)
    assert len(results_2) <= 2


def test_faz93_empty_index_empty_results() -> None:
    """Empty docs -> build_index -> search returns []."""
    index = build_index([])
    assert index.search("anything", 5) == []


def test_faz93_no_match_empty_results() -> None:
    """Query with no matching token returns []."""
    docs = [ingest_doc(FIXTURES_DOCS / "note_a.txt")]
    index = build_index(docs)
    # Token that doesn't appear (e.g. xyzzz)
    results = index.search("xyzzz", 5)
    assert results == []
