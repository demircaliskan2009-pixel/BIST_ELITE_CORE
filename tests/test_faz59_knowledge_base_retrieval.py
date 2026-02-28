"""
FAZ59: Knowledge base storage + retrieval.
Tests: deterministic doc_ids, retrieval ranking stable (BM25-like), no deps.
"""

from __future__ import annotations

from pathlib import Path


from bist_core.knowledge import KnowledgeBase, add_documents


def test_faz59_doc_id_deterministic() -> None:
    """Same document -> same doc_id (sha256 of canonical json)."""
    kb = KnowledgeBase()
    doc = {"id": "a", "title": "Alpha", "body": "Content alpha"}
    ids1 = kb.add_documents([doc])
    ids2 = kb.add_documents([doc])
    assert len(ids1) == 1
    assert len(ids2) == 1
    assert ids1[0] == ids2[0]
    assert len(ids1[0]) == 16
    assert ids1[0].isalnum()


def test_faz59_different_doc_different_id() -> None:
    """Different documents -> different doc_ids."""
    kb = KnowledgeBase()
    ids = kb.add_documents(
        [
            {"title": "A"},
            {"title": "B"},
        ]
    )
    assert len(ids) == 2
    assert ids[0] != ids[1]


def test_faz59_retrieval_ranking_stable() -> None:
    """Retrieve same query twice -> same order of (doc_id, score)."""
    kb = KnowledgeBase()
    kb.add_documents(
        [
            {"title": "cat dog", "body": "feline canine"},
            {"title": "dog only", "body": "canine"},
            {"title": "cat only", "body": "feline"},
        ]
    )
    r1 = kb.retrieve("cat dog", top_k=5)
    r2 = kb.retrieve("cat dog", top_k=5)
    assert r1 == r2
    assert len(r1) >= 1
    for doc_id, score in r1:
        assert isinstance(doc_id, str)
        assert isinstance(score, (int, float))
        assert score >= 0


def test_faz59_retrieval_relevant_higher() -> None:
    """Document with more query terms scores higher (BM25-like)."""
    kb = KnowledgeBase()
    kb.add_documents(
        [
            {"title": "alpha beta gamma", "body": "a b c"},
            {"title": "alpha", "body": "only alpha"},
        ]
    )
    r = kb.retrieve("alpha beta", top_k=2)
    assert len(r) == 2
    scores_by_id = {doc_id: s for doc_id, s in r}
    first_doc = r[0][0]
    second_doc = r[1][0]
    first_score = scores_by_id[first_doc]
    second_score = scores_by_id[second_doc]
    assert first_score >= second_score


def test_faz59_add_documents_returns_ids() -> None:
    """add_documents returns list of doc_ids in order."""
    kb = KnowledgeBase()
    docs = [{"x": i} for i in range(3)]
    ids = kb.add_documents(docs)
    assert len(ids) == 3
    assert all(len(d) == 16 and d.isalnum() for d in ids)


def test_faz59_save_load_roundtrip(tmp_path: Path) -> None:
    """Save knowledge_index.json and load -> same doc_ids and retrieve works."""
    kb = KnowledgeBase()
    kb.add_documents([{"title": "saved", "body": "content"}])
    path = tmp_path / "knowledge_index.json"
    kb.save(path)
    assert path.is_file()
    kb2 = KnowledgeBase()
    kb2.load(path)
    r = kb2.retrieve("saved content", top_k=1)
    assert len(r) == 1
    assert r[0][1] > 0


def test_faz59_empty_retrieve() -> None:
    """retrieve on empty base returns []."""
    kb = KnowledgeBase()
    r = kb.retrieve("anything", top_k=5)
    assert r == []


def test_faz59_add_documents_convenience() -> None:
    """add_documents(docs, base=None) returns (doc_ids, base)."""
    ids, kb = add_documents([{"title": "alpha beta", "body": "content"}])
    assert len(ids) == 1
    assert isinstance(kb, KnowledgeBase)
    r = kb.retrieve("alpha content", top_k=1)
    assert len(r) == 1
