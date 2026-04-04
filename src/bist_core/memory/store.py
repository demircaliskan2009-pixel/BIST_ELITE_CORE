"""
FAZ92: Doc store — put/get by sha256 key (doc_id).
Store root; key = doc_id (sha256 hex); value = raw bytes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from bist_core.services import snapshot_integrity


def put_doc(store_root: Path | str, doc_id: str, data: bytes) -> str:
    """
    Write data to store_root/doc_id. doc_id is used as filename (sha256 hex).
    Returns sha256 hex of written file (for verification).
    """
    root = Path(store_root)
    path = root / doc_id
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return snapshot_integrity.compute_sha256(path)


def get_doc(store_root: Path | str, doc_id: str) -> Optional[bytes]:
    """Read store_root/doc_id; return bytes or None if missing."""
    path = Path(store_root) / doc_id
    if not path.is_file():
        return None
    return path.read_bytes()


__all__ = ["put_doc", "get_doc"]
