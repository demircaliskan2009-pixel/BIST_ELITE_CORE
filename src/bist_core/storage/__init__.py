"""Storage contracts (snapshot store, etc.)."""
from __future__ import annotations

from bist_core.storage.snapshots import get_snapshot, put_snapshot, snapshot_sha256

__all__ = ["put_snapshot", "get_snapshot", "snapshot_sha256"]
