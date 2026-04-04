"""Symbol ranking by edge_score (dict-based)."""

from __future__ import annotations

from bist_core.brain.ranking_engine import rank_symbols


def test_ranking_order() -> None:
    data = [
        {"symbol": "A", "edge_score": 0.2},
        {"symbol": "B", "edge_score": 0.8},
        {"symbol": "C", "edge_score": 0.5},
    ]
    ranked = rank_symbols(data)
    assert ranked[0]["symbol"] == "B"
    assert ranked[-1]["symbol"] == "A"
