"""Tests for Ranking Engine — ranked decisions from scan candidates."""

from __future__ import annotations

import pytest

from bist_core.rank import Ranker, normalize_weights
from bist_core.rank.weights import InvalidWeightsError


def _candidate(symbol: str, momentum: float, volatility: float, score_modifier: float = 1.0) -> dict:
    return {
        "symbol": symbol,
        "momentum": momentum,
        "volatility": volatility,
        "score_modifier": score_modifier,
        "reasons": {},
    }


def test_basic_ranking() -> None:
    """Rank candidates by score."""
    weights = {"momentum": 0.7, "volatility": 0.3}
    ranker = Ranker(weights)
    candidates = [
        _candidate("A", 10.0, 2.0),
        _candidate("B", 5.0, 5.0),
        _candidate("C", 0.0, 0.0),
    ]
    ranked = ranker.rank(candidates, top_n=5)
    assert len(ranked) == 3
    assert ranked[0]["symbol"] == "A"
    assert ranked[0]["score"] == 10.0 * 0.7 + 2.0 * 0.3
    assert "momentum" in ranked[0]
    assert "volatility" in ranked[0]
    assert "score_modifier" in ranked[0]
    assert "reasons" in ranked[0]


def test_weight_normalization() -> None:
    """Weights are normalized to sum 1."""
    weights = {"momentum": 2.0, "volatility": 2.0}
    norm = normalize_weights(weights)
    assert abs(sum(norm.values()) - 1.0) < 1e-9
    assert norm["momentum"] == 0.5
    assert norm["volatility"] == 0.5

    with pytest.raises(InvalidWeightsError) as exc_info:
        normalize_weights({})
    assert "empty" in str(exc_info.value).lower()


def test_invalid_candidate_skipped() -> None:
    """Invalid candidates are skipped."""
    weights = {"momentum": 0.5, "volatility": 0.5}
    ranker = Ranker(weights)
    candidates = [
        _candidate("VALID", 10.0, 2.0),
        {"symbol": "MISSING_FIELDS"},
        _candidate("ALSO_VALID", 5.0, 1.0),
    ]
    ranked = ranker.rank(candidates, top_n=5)
    assert len(ranked) == 2
    symbols = {r["symbol"] for r in ranked}
    assert symbols == {"ALSO_VALID", "VALID"}


def test_determinism() -> None:
    """Same input produces same output."""
    weights = {"momentum": 0.5, "volatility": 0.5}
    ranker = Ranker(weights)
    candidates = [
        _candidate("A", 1.0, 1.0),
        _candidate("B", 2.0, 2.0),
    ]
    a = ranker.rank(candidates)
    b = ranker.rank(candidates)
    assert a == b


def test_tie_breaker() -> None:
    """Tie on score → sort by symbol alphabetical."""
    weights = {"momentum": 0.5, "volatility": 0.5}
    ranker = Ranker(weights)
    candidates = [
        _candidate("Z", 1.0, 1.0),
        _candidate("A", 1.0, 1.0),
        _candidate("M", 1.0, 1.0),
    ]
    ranked = ranker.rank(candidates, top_n=5)
    assert [r["symbol"] for r in ranked] == ["A", "M", "Z"]


def test_empty_input() -> None:
    """Empty candidates returns empty list."""
    weights = {"momentum": 0.5, "volatility": 0.5}
    ranker = Ranker(weights)
    assert ranker.rank([]) == []


def test_top_n_limit() -> None:
    """top_n limits results."""
    weights = {"momentum": 0.5, "volatility": 0.5}
    ranker = Ranker(weights)
    candidates = [
        _candidate("A", 10.0, 0.0),
        _candidate("B", 5.0, 0.0),
        _candidate("C", 1.0, 0.0),
    ]
    ranked = ranker.rank(candidates, top_n=2)
    assert len(ranked) == 2
    assert ranked[0]["symbol"] == "A"
    assert ranked[1]["symbol"] == "B"


def test_score_modifier_applied() -> None:
    """score_modifier affects final score."""
    weights = {"momentum": 1.0, "volatility": 0.0}
    ranker = Ranker(weights)
    c = _candidate("X", 10.0, 0.0, score_modifier=0.5)
    result = ranker.score(c)
    assert result["score"] == 5.0
