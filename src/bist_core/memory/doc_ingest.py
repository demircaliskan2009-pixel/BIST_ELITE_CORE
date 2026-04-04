"""
FAZ92: Doc ingest — content -> doc with doc_id = sha256(content).
Same content -> same doc_id (deterministic). No network.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict, Union


def doc_id_from_content(content: Union[bytes, str]) -> str:
    """
    Deterministic doc_id = sha256(content). str is encoded as utf-8.
    Same content -> same doc_id.
    """
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def ingest_doc(
    content: Union[bytes, str, Path],
    *,
    source: str = "",
) -> Dict[str, Any]:
    """
    Ingest content (bytes, str, or path to file) into a doc dict.
    Returns { "doc_id": sha256_hex, "content": bytes, "source": source }.
    Same content -> same doc_id.
    """
    if isinstance(content, Path):
        raw = content.read_bytes()
        source_str = source or str(content)
    elif isinstance(content, str):
        raw = content.encode("utf-8")
        source_str = source or ""
    else:
        raw = content
        source_str = source or ""

    doc_id = hashlib.sha256(raw).hexdigest()
    return {
        "doc_id": doc_id,
        "content": raw,
        "source": source_str,
    }


__all__ = ["doc_id_from_content", "ingest_doc"]
