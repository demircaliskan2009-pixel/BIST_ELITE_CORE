"""
FAZ84: Snapshot store contract — put/get/sha256.
Deterministic: path and sha256 in artifact form for pipeline manifest.
No external deps; uses Path and snapshot_integrity for hashing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from bist_core.services import snapshot_integrity


def put_snapshot(store_root: Path | str, key: str, data: bytes) -> Dict[str, Any]:
    """
    Write data to store_root/key. Return artifact dict {path, sha256}.
    Path is the resolved file path; sha256 is hex digest of file content.
    """
    root = Path(store_root)
    path = root / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    sha = snapshot_integrity.compute_sha256(path)
    return {"path": str(path.resolve()), "sha256": sha}


def get_snapshot(store_root: Path | str, key: str) -> Optional[bytes]:
    """Read store_root/key; return bytes or None if missing."""
    path = Path(store_root) / key
    if not path.is_file():
        return None
    return path.read_bytes()


def snapshot_sha256(store_root: Path | str, key: str) -> Optional[str]:
    """Return sha256 hex of store_root/key, or None if missing."""
    path = Path(store_root) / key
    if not path.is_file():
        return None
    return snapshot_integrity.compute_sha256(path)


__all__ = ["put_snapshot", "get_snapshot", "snapshot_sha256"]
