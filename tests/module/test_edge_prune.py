"""edge_prune — deterministic top-N."""

from __future__ import annotations

from bist_core.edge.edge_prune import prune_edges_top_n


def test_prune_keeps_top_by_abs_exp() -> None:
    edges = {
        (0,): {"exp": 0.01, "count": 10},
        (1,): {"exp": -0.5, "count": 100},
        (2,): {"exp": 0.2, "count": 5},
    }
    out = prune_edges_top_n(edges, 2)
    assert len(out) == 2
    assert (1,) in out and (2,) in out


def test_prune_noop_when_small() -> None:
    e = {(0,): {"exp": 0.1, "count": 1}}
    assert prune_edges_top_n(e, 10) == e
