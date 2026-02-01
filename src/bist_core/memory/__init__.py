"""FAZ92: Document ingest (sha256 doc_id) + store by sha256 key."""
from __future__ import annotations

from bist_core.memory.doc_ingest import doc_id_from_content, ingest_doc
from bist_core.memory.store import get_doc, put_doc

__all__ = ["doc_id_from_content", "ingest_doc", "put_doc", "get_doc"]
