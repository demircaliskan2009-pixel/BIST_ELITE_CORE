"""
FAZ59: Knowledge base storage + retrieval (no external vector db).
Deterministic doc_id = sha256(canonical json). BM25-like token overlap retrieval (stdlib only).
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _tokenize(text: str, min_len: int = 2) -> List[str]:
    """Lowercase alphanumeric tokens of length >= min_len. Deterministic."""
    if not text:
        return []
    tokens = re.findall(r"\b[a-z0-9]{" + str(min_len) + r",}\b", text.lower())
    return tokens


def _doc_id(doc: Dict[str, Any]) -> str:
    """Deterministic doc_id from canonical JSON. SHA256 hex first 16 chars."""
    canonical = json.dumps(doc, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _doc_text(doc: Dict[str, Any]) -> str:
    """Canonical text for indexing: sorted key-value pairs joined."""
    parts = []
    for k in sorted(doc.keys()):
        v = doc.get(k)
        if v is not None and v != "":
            parts.append(f"{k} {v}" if isinstance(v, str) else f"{k} {json.dumps(v, sort_keys=True)}")
    return " ".join(parts)


class KnowledgeBase:
    """In-memory knowledge base: add_documents (deterministic doc_id), retrieve (BM25-like). Stdlib only."""

    def __init__(self) -> None:
        self._doc_ids: List[str] = []
        self._documents: Dict[str, Dict[str, Any]] = {}  # doc_id -> {text, tokens, tf}
        self._df: Dict[str, int] = {}  # term -> doc frequency
        self._N: int = 0

    def add_documents(self, documents: List[Dict[str, Any]]) -> List[str]:
        """
        Add documents; assign deterministic doc_id = sha256(canonical json)[:16].
        Returns list of doc_ids in order. Indexes text for retrieval.
        """
        ids_out: List[str] = []
        for doc in documents:
            if not isinstance(doc, dict):
                continue
            doc_id = _doc_id(doc)
            text = _doc_text(doc)
            tokens = _tokenize(text)
            if doc_id in self._documents:
                ids_out.append(doc_id)
                continue
            tf: Dict[str, int] = {}
            for t in tokens:
                tf[t] = tf.get(t, 0) + 1
            self._documents[doc_id] = {"text": text, "tokens": tokens, "tf": tf}
            self._doc_ids.append(doc_id)
            self._N += 1
            for t in tf:
                self._df[t] = self._df.get(t, 0) + 1
            ids_out.append(doc_id)
        return ids_out

    def retrieve(
        self,
        query: str,
        top_k: int = 10,
        k1: float = 1.5,
    ) -> List[Tuple[str, float]]:
        """
        BM25-like retrieval: score = sum over query terms of tf * idf.
        idf(t) = log((N - df + 0.5) / (df + 0.5) + 1). Stable sort by score desc, then doc_id asc.
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
        ranked = sorted(scores.items(), key=lambda x: (-x[1], x[0]))[:top_k]
        return ranked

    def save(self, path: Path | str) -> None:
        """Write knowledge_index.json: doc_ids, documents (text, tf), df, N."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "doc_ids": self._doc_ids,
            "documents": {doc_id: {"text": meta["text"], "tf": meta["tf"]} for doc_id, meta in self._documents.items()},
            "df": self._df,
            "N": self._N,
        }
        tmp = path.with_name(path.name + ".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        tmp.replace(path)

    def load(self, path: Path | str) -> None:
        """Load knowledge_index.json and rebuild in-memory index."""
        path = Path(path)
        if not path.is_file():
            return
        data = json.loads(path.read_text(encoding="utf-8"))
        self._doc_ids = data.get("doc_ids") or []
        self._df = data.get("df") or {}
        self._N = int(data.get("N") or 0)
        self._documents = {}
        for doc_id, meta in (data.get("documents") or {}).items():
            tf = meta.get("tf") or {}
            text = meta.get("text") or ""
            tokens = _tokenize(text)
            self._documents[doc_id] = {"text": text, "tokens": tokens, "tf": tf}


def add_documents(
    documents: List[Dict[str, Any]], base: Optional[KnowledgeBase] = None
) -> Tuple[List[str], KnowledgeBase]:
    """Convenience: add documents to base (or new), return (doc_ids, base)."""
    if base is None:
        base = KnowledgeBase()
    ids_out = base.add_documents(documents)
    return ids_out, base
