"""FAZ59: Knowledge base storage + retrieval (no external vector db). Deterministic doc_id, BM25-like retrieval."""
from __future__ import annotations

from bist_core.knowledge.store import KnowledgeBase, add_documents

__all__ = ["KnowledgeBase", "add_documents"]
