"""Ranking engine — scores and ranks trading decisions by signal strength.

Pure deterministic scoring: confidence × reward/risk ratio.
No network, no numpy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Sequence

from bist_core.brain.strategy_engine import Decision


@dataclass
class RankedSignal:
    symbol: str
    score: float
    confidence: float
    entry: float
    stop: float
    target: float
    side: str
    reasoning: str
    timestamp: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "score": self.score,
            "confidence": self.confidence,
            "entry": self.entry,
            "stop": self.stop,
            "target": self.target,
            "side": self.side,
            "reasoning": self.reasoning,
            "timestamp": self.timestamp,
        }


class RankingEngine:
    """Score and rank Decision objects deterministically."""

    def __init__(self, max_candidates: int = 50) -> None:
        self._max_candidates = max_candidates

    @property
    def max_candidates(self) -> int:
        return self._max_candidates

    def score_decision(self, decision: Decision) -> float:
        stop_distance = abs(decision.entry - decision.stop)
        if stop_distance <= 0:
            return 0.0
        reward = abs(decision.target - decision.entry)
        reward_risk = reward / stop_distance
        if reward_risk <= 0:
            return 0.0
        return round(decision.confidence * reward_risk, 6)

    def rank_decisions(self, decisions: Sequence[Decision]) -> List[RankedSignal]:
        scored: list[tuple[float, str, Decision]] = []
        for d in decisions:
            s = self.score_decision(d)
            scored.append((s, d.symbol, d))

        scored.sort(key=lambda x: (-x[0], x[1]))

        ranked: list[RankedSignal] = []
        for score, _, d in scored[: self._max_candidates]:
            ranked.append(RankedSignal(
                symbol=d.symbol,
                score=score,
                confidence=d.confidence,
                entry=d.entry,
                stop=d.stop,
                target=d.target,
                side=d.side,
                reasoning=d.reasoning,
                timestamp=d.timestamp,
            ))
        return ranked

    def top_n(self, decisions: Sequence[Decision], n: int) -> List[RankedSignal]:
        ranked = self.rank_decisions(decisions)
        return ranked[:max(n, 0)]


def rank_symbols(decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Input: list of decision dicts (each includes edge_score)
    Output: sorted list (best → worst)
    """

    filtered = [
        d for d in decisions
        if d.get("edge_score", 0.0) > 0.05
    ]

    ranked = sorted(
        filtered,
        key=lambda d: d["edge_score"],
        reverse=True
    )

    return ranked


__all__ = [
    "RankedSignal",
    "RankingEngine",
    "rank_symbols",
]
