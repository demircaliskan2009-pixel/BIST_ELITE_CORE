"""In-memory edge maps — historical + live (live takes priority on lookup)."""

from __future__ import annotations

from typing import Any

from bist_core.edge.edge_prune import prune_edges_top_n


class EdgeStore:
    def __init__(self) -> None:
        self.historical_edges: dict[tuple[Any, ...], dict[str, Any]] = {}
        self.live_edges: dict[tuple[Any, ...], dict[str, Any]] = {}
        self.live_loaded_cycle: int = 0
        self.edges_by_tf: dict[str, dict[tuple[Any, ...], dict[str, Any]]] = {}

    def load(self, edges: dict[tuple[Any, ...], dict[str, Any]]) -> None:
        self.historical_edges = dict(edges)

    def load_live(
        self,
        edges: dict[tuple[Any, ...], dict[str, Any]],
        loaded_cycle: int,
        *,
        max_edges: int = 500,
    ) -> None:
        """Replace live edge map (pruned to top ``max_edges`` by |exp|); decay uses ``loaded_cycle``."""
        self.live_edges = prune_edges_top_n(dict(edges), max_edges)
        self.live_loaded_cycle = int(loaded_cycle)

    def load_by_tf(self, edges_by_tf: dict[str, dict[tuple[Any, ...], dict[str, Any]]]) -> None:
        self.edges_by_tf = {str(k): dict(v) for k, v in edges_by_tf.items()}

    def get(self, key: tuple[Any, ...], *, edge_cycle: int | None = None) -> dict[str, Any] | None:
        """Prefer live edges over historical; apply recency decay to live when ``edge_cycle`` set."""
        live = self.live_edges.get(key)
        if isinstance(live, dict):
            out = dict(live)
            if edge_cycle is not None:
                cycles_old = max(0, int(edge_cycle) - self.live_loaded_cycle)
                decay = 1.0 / (1.0 + 0.01 * float(cycles_old))
                exp = float(out.get("exp", 0.0)) * decay
                conf = float(out.get("confidence", out.get("exp", 0.0))) * decay
                out["exp"] = exp
                out["confidence"] = conf
            return out
        hist = self.historical_edges.get(key)
        return dict(hist) if isinstance(hist, dict) else None

    def get_tf(self, tf: str, key: tuple[Any, ...]) -> dict[str, Any] | None:
        out = self.edges_by_tf.get(str(tf), {}).get(key)
        return out if isinstance(out, dict) else None


__all__ = ["EdgeStore"]
