from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from bist_core.brain.regime_engine import NO_REGIME, MarketRegime
from bist_core.brain.scoring_engine import _is_regime_compatible, score_edges
from bist_core.edge.registry import EdgeDefinition, EdgeRegistry
from bist_core.models.ohlcv import OHLCVBar


@dataclass(frozen=True)
class EdgeSelectionResult:
    selected_edge_id: str | None
    score: float
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected_edge_id": self.selected_edge_id,
            "score": self.score,
            "explanation": self.explanation,
        }


def _regime_label(regime: MarketRegime | Mapping[str, Any]) -> str | None:
    if isinstance(regime, MarketRegime):
        return str(regime.regime or "").strip() or None
    if isinstance(regime, Mapping):
        label = regime.get("regime") or regime.get("label")
        token = str(label or "").strip()
        return token or None
    return None


def select_best_edge(
    edges: Sequence[EdgeDefinition],
    regime: MarketRegime | Mapping[str, Any],
    bars: Sequence[OHLCVBar],
    edge_states: Mapping[str, Any] | None = None,
) -> EdgeSelectionResult:
    if not edges:
        return EdgeSelectionResult(None, 0.0, "NO TRADE: no_edges")

    if edge_states is not None:
        from bist_core.edge.self_healing import filter_edges_for_selection

        edges = filter_edges_for_selection(edges, edge_states)
        if not edges:
            return EdgeSelectionResult(None, 0.0, "NO TRADE: no_active_edges_after_state_filter")

    regime_label = _regime_label(regime)
    if regime_label is None:
        return EdgeSelectionResult(None, 0.0, "NO TRADE: insufficient_regime_context")
    if regime_label == NO_REGIME:
        return EdgeSelectionResult(None, 0.0, "NO TRADE: no_regime")

    compatible_edges = [edge for edge in edges if edge.enabled and _is_regime_compatible(edge, regime_label)]
    if not compatible_edges:
        return EdgeSelectionResult(None, 0.0, f"NO TRADE: no_compatible_edges:{regime_label}")

    try:
        registry = EdgeRegistry(edges=compatible_edges)
    except ValueError as exc:
        return EdgeSelectionResult(None, 0.0, f"NO TRADE: invalid_edge_set:{exc}")

    results = score_edges(registry, regime, bars)
    positive_results = [result for result in results if result.total_score > 0.0]
    if not positive_results:
        return EdgeSelectionResult(None, 0.0, "NO TRADE: all_scores_zero")

    best_score = max(result.total_score for result in positive_results)
    top_results = [result for result in positive_results if result.total_score == best_score]
    if len(top_results) != 1:
        tied_ids = ",".join(sorted(result.edge_id for result in top_results))
        return EdgeSelectionResult(None, 0.0, f"NO TRADE: ambiguous_top_score:{tied_ids}")

    best = top_results[0]
    return EdgeSelectionResult(
        selected_edge_id=best.edge_id,
        score=best.total_score,
        explanation=f"selected_edge_id={best.edge_id}; score={best.total_score:.4f}; {best.explanation}",
    )


__all__ = ["EdgeSelectionResult", "select_best_edge"]
