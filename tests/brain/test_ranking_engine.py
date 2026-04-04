"""Ranking engine unit tests — scoring, ranking, top-N, determinism."""

from __future__ import annotations

import pytest

from bist_core.brain.ranking_engine import RankedSignal, RankingEngine
from bist_core.brain.strategy_engine import Decision


def _decision(
    symbol: str = "X",
    entry: float = 100.0,
    stop: float = 95.0,
    target: float = 110.0,
    confidence: float = 1.0,
    side: str = "long",
) -> Decision:
    return Decision(
        symbol=symbol,
        entry=entry,
        stop=stop,
        target=target,
        side=side,
        confidence=confidence,
        reasoning="test",
        timestamp=1_704_067_200,
    )


class TestScoreDecision:
    def test_score_decision_valid(self) -> None:
        engine = RankingEngine()
        d = _decision(entry=100, stop=95, target=110, confidence=1.5)
        score = engine.score_decision(d)
        expected = 1.5 * (10.0 / 5.0)
        assert score == pytest.approx(expected, abs=0.001)

    def test_score_decision_invalid_stop_distance(self) -> None:
        engine = RankingEngine()
        d = _decision(entry=100, stop=100, target=110)
        assert engine.score_decision(d) == 0.0

    def test_score_decision_target_equals_entry(self) -> None:
        engine = RankingEngine()
        d = _decision(entry=100, stop=95, target=100)
        assert engine.score_decision(d) == 0.0

    def test_score_decision_short(self) -> None:
        engine = RankingEngine()
        d = _decision(entry=100, stop=105, target=90, confidence=2.0, side="short")
        score = engine.score_decision(d)
        expected = 2.0 * (10.0 / 5.0)
        assert score == pytest.approx(expected, abs=0.001)


class TestRankDecisions:
    def test_rank_decisions_sorted_descending(self) -> None:
        engine = RankingEngine()
        decisions = [
            _decision("A", confidence=1.0),
            _decision("B", confidence=3.0),
            _decision("C", confidence=2.0),
        ]
        ranked = engine.rank_decisions(decisions)
        scores = [r.score for r in ranked]
        assert scores == sorted(scores, reverse=True)
        assert ranked[0].symbol == "B"

    def test_rank_decisions_tiebreak_by_symbol(self) -> None:
        engine = RankingEngine()
        decisions = [
            _decision("Z", confidence=1.0),
            _decision("A", confidence=1.0),
        ]
        ranked = engine.rank_decisions(decisions)
        assert ranked[0].symbol == "A"
        assert ranked[1].symbol == "Z"

    def test_rank_decisions_respects_max_candidates(self) -> None:
        engine = RankingEngine(max_candidates=2)
        decisions = [_decision(f"S{i}", confidence=float(i)) for i in range(5)]
        ranked = engine.rank_decisions(decisions)
        assert len(ranked) == 2

    def test_rank_decisions_empty(self) -> None:
        engine = RankingEngine()
        assert engine.rank_decisions([]) == []


class TestTopN:
    def test_top_n_returns_limited_results(self) -> None:
        engine = RankingEngine()
        decisions = [_decision(f"S{i}", confidence=float(i)) for i in range(10)]
        top = engine.top_n(decisions, 3)
        assert len(top) == 3
        assert top[0].score >= top[1].score >= top[2].score

    def test_top_n_zero(self) -> None:
        engine = RankingEngine()
        assert engine.top_n([_decision()], 0) == []

    def test_top_n_greater_than_available(self) -> None:
        engine = RankingEngine()
        decisions = [_decision("A"), _decision("B")]
        top = engine.top_n(decisions, 100)
        assert len(top) == 2


class TestRankedSignal:
    def test_to_dict(self) -> None:
        sig = RankedSignal(
            symbol="GARAN", score=3.5, confidence=1.2,
            entry=30.0, stop=28.0, target=35.0, side="long",
            reasoning="test", timestamp=1_704_067_200,
        )
        d = sig.to_dict()
        assert d["symbol"] == "GARAN"
        assert d["score"] == 3.5


class TestDeterminism:
    def test_deterministic_ranking_same_input_same_output(self) -> None:
        engine = RankingEngine()
        decisions = [
            _decision("C", confidence=2.0),
            _decision("A", confidence=3.0),
            _decision("B", confidence=1.0),
        ]
        r1 = [s.to_dict() for s in engine.rank_decisions(decisions)]
        r2 = [s.to_dict() for s in engine.rank_decisions(decisions)]
        assert r1 == r2
