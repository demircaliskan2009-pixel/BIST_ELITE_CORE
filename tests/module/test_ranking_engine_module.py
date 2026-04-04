"""Tests for Ranking Engine — rank scanner outputs into best trade candidates."""

from __future__ import annotations

import math

from bist_core.ranking import RankingEngine


def _candidate(symbol: str, score: float, signal_strength: float, volatility: float, trend: str) -> dict:
    return {
        "symbol": symbol,
        "score": score,
        "signal_strength": signal_strength,
        "volatility": volatility,
        "trend": trend,
    }


def test_deterministic_behavior() -> None:
    """Same input produces same output."""
    candidates = [
        _candidate("A", 0.8, 0.7, 0.05, "up"),
        _candidate("B", 0.6, 0.5, 0.03, "down"),
    ]
    engine = RankingEngine()
    a = engine.rank(candidates)
    b = engine.rank(candidates)
    assert a == b


def test_sorting_correctness() -> None:
    """Results sorted by final_score descending, rank 1..n."""
    candidates = [
        _candidate("LOW", 0.2, 0.1, 0.01, "down"),
        _candidate("HIGH", 0.9, 0.9, 0.08, "up"),
        _candidate("MID", 0.5, 0.5, 0.04, "neutral"),
    ]
    engine = RankingEngine()
    results = engine.rank(candidates)
    assert len(results) == 3
    scores = [r["final_score"] for r in results]
    assert scores == sorted(scores, reverse=True)
    assert results[0]["symbol"] == "HIGH"
    assert results[0]["rank"] == 1
    assert results[1]["rank"] == 2
    assert results[2]["rank"] == 3


def test_invalid_filtering() -> None:
    """Skip candidates with missing fields, NaN, or invalid types."""
    candidates = [
        _candidate("VALID", 0.5, 0.5, 0.03, "up"),
        {"symbol": "MISSING", "score": 0.5},
        _candidate("NAN", math.nan, 0.5, 0.03, "up"),
        _candidate("BAD_TYPE", "not_float", 0.5, 0.03, "up"),
    ]
    engine = RankingEngine()
    results = engine.rank(candidates)
    assert len(results) == 1
    assert results[0]["symbol"] == "VALID"


def test_confidence_bounds() -> None:
    """Confidence is clamped to [0, 1]."""
    candidates = [
        _candidate("A", 0.5, 0.5, 0.05, "up"),
    ]
    engine = RankingEngine()
    results = engine.rank(candidates)
    assert len(results) == 1
    assert 0 <= results[0]["confidence"] <= 1


def test_output_schema() -> None:
    """Each result has symbol, final_score, confidence, rank."""
    candidates = [_candidate("X", 0.8, 0.7, 0.04, "up")]
    engine = RankingEngine()
    results = engine.rank(candidates)
    assert len(results) == 1
    r = results[0]
    assert "symbol" in r
    assert "final_score" in r
    assert "confidence" in r
    assert "rank" in r


def test_empty_input() -> None:
    """Empty candidates returns empty list."""
    engine = RankingEngine()
    assert engine.rank([]) == []


def test_all_invalid() -> None:
    """All invalid returns empty list."""
    candidates = [
        {"symbol": "X"},
        {"score": 0.5},
    ]
    engine = RankingEngine()
    assert engine.rank(candidates) == []
