"""
FAZ93: Keyword retrieval — build_index(docs) -> search(query, k).
Deterministic scoring: same docs + same query -> same order and scores.
Docs: list of dicts with doc_id and content (bytes). Stdlib only.
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Tuple

# Default BM25-like constants for deterministic scoring
DEFAULT_K1 = 1.5


def _tokenize(text: str, min_len: int = 2) -> List[str]:
    """Lowercase alphanumeric tokens of length >= min_len. Deterministic."""
    if not text:
        return []
    tokens = re.findall(r"\b[a-z0-9]{" + str(min_len) + r",}\b", text.lower())
    return tokens


def _doc_text(doc: Dict[str, Any]) -> str:
    """Extract searchable text from doc: content (bytes decoded) or empty."""
    content = doc.get("content")
    if content is None:
        return ""
    if isinstance(content, bytes):
        try:
            return content.decode("utf-8", errors="replace")
        except Exception:
            return ""
    if isinstance(content, str):
        return content
    return ""


class _Index:
    """In-memory index: doc_id -> {text, tokens, tf}; df, N for idf."""

    def __init__(self) -> None:
        self._doc_ids: List[str] = []
        self._documents: Dict[str, Dict[str, Any]] = {}
        self._df: Dict[str, int] = {}
        self._N: int = 0

    def search(self, query: str, k: int = 10, *, k1: float = DEFAULT_K1) -> List[Tuple[str, float]]:
        """
        BM25-like keyword search. Deterministic: score rounded to 6 decimals;
        sort by (-score, doc_id). Returns list of (doc_id, score).
        """
        if self._N == 0:
            return []
        q_tokens = _tokenize(query)
        if not q_tokens:
            return []
        scores: Dict[str, float] = {}
        for doc_id, meta in self._documents.items():
            tf_d = meta["tf"]
            s = 0.0
            for t in q_tokens:
                if t not in tf_d:
                    continue
                df_t = self._df.get(t, 0)
                idf = math.log((self._N - df_t + 0.5) / (df_t + 0.5) + 1.0)
                tf_val = tf_d[t]
                s += tf_val * (k1 + 1) / (tf_val + k1) * idf
            if s > 0:
                scores[doc_id] = round(s, 6)
        ranked = sorted(scores.items(), key=lambda x: (-x[1], x[0]))[:k]
        return ranked


def build_index(docs: List[Dict[str, Any]]) -> _Index:
    """
    Build in-memory keyword index from docs. Each doc must have doc_id and content (bytes or str).
    Same docs -> same index -> deterministic search scores.
    """
    idx = _Index()
    for doc in docs or []:
        if not isinstance(doc, dict):
            continue
        doc_id = doc.get("doc_id")
        if not doc_id or not isinstance(doc_id, str):
            continue
        if doc_id in idx._documents:
            continue
        text = _doc_text(doc)
        tokens = _tokenize(text)
        tf: Dict[str, int] = {}
        for t in tokens:
            tf[t] = tf.get(t, 0) + 1
        idx._documents[doc_id] = {"text": text, "tokens": tokens, "tf": tf}
        idx._doc_ids.append(doc_id)
        idx._N += 1
        for t in tf:
            idx._df[t] = idx._df.get(t, 0) + 1
    return idx


__all__ = ["build_index", "DEFAULT_K1"]
