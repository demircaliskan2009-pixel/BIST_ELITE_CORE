"""Deterministic edge-map size limits (explosion guard)."""

from __future__ import annotations

from typing import Any


def prune_edges_top_n(
    edges: dict[tuple[Any, ...], dict[str, Any]],
    max_edges: int,
) -> dict[tuple[Any, ...], dict[str, Any]]:
    """Keep top N buckets by |exp| then count."""
    n = max(1, int(max_edges))
    if len(edges) <= n:
        return dict(edges)

    def sort_key(item: tuple[tuple[Any, ...], dict[str, Any]]) -> tuple[float, float]:
        _k, rec = item
        exp = float(rec.get("exp", 0.0)) if isinstance(rec, dict) else 0.0
        cnt = float(rec.get("count", 0.0)) if isinstance(rec, dict) else 0.0
        return (abs(exp), cnt)

    ranked = sorted(edges.items(), key=sort_key, reverse=True)
    return dict(ranked[:n])


__all__ = ["prune_edges_top_n"]
