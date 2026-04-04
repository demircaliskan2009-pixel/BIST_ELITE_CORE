"""Per-timeframe edge lookup from nested edge maps."""

from __future__ import annotations

from typing import Any

from bist_core.edge.bucket_key import edge_bucket_key


class MultiTFEdge:
    """``edges[tf][bucket_key] -> {exp, count}``."""

    def __init__(self, edges: dict[str, dict[tuple[Any, ...], dict[str, Any]]]) -> None:
        self.edges = edges

    def get(self, tf: str, feat: dict[str, Any]) -> dict[str, Any] | None:
        key = edge_bucket_key(feat)
        out = self.edges.get(str(tf), {}).get(key)
        return out if isinstance(out, dict) else None


__all__ = ["MultiTFEdge"]
