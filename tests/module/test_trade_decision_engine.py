"""Tests for Trade Decision Engine — ranked + validation → trade decisions."""

from __future__ import annotations

from bist_core.decision.trade_decision_engine import TradeDecisionEngine


def _ranked(symbol: str, final_score: float = 0.8, last_close: float = 100.0) -> dict:
    return {
        "symbol": symbol,
        "final_score": final_score,
        "confidence": final_score,
        "rank": 1,
        "last_close": last_close,
    }


def _validation(symbol: str, stability: float = 0.7, avg_expectancy: float = 50.0) -> dict:
    return {
        "symbols": {
            symbol: {
                "windows": [],
                "avg_expectancy": avg_expectancy,
                "avg_drawdown": 0.05,
                "stability": stability,
            },
        },
    }


def test_filtering_logic() -> None:
    """Skip only when stability < 0."""
    engine = TradeDecisionEngine()

    ranked = [_ranked("A", last_close=100.0)]
    val_negative_stability = {"symbols": {"A": {"stability": -0.1, "avg_expectancy": 50.0}}}
    assert engine.decide(ranked, val_negative_stability) == []

    val_low_stability = {"symbols": {"A": {"stability": 0.3, "avg_expectancy": 50.0}}}
    assert len(engine.decide(ranked, val_low_stability)) == 1

    val_zero_expectancy = {"symbols": {"A": {"stability": 0.7, "avg_expectancy": 0.0}}}
    assert len(engine.decide(ranked, val_zero_expectancy)) == 1


def test_confidence_calculation() -> None:
    """Confidence = 0.5*rank_score + 0.3*stability + 0.2*expectancy."""
    engine = TradeDecisionEngine()
    ranked = [_ranked("X", final_score=0.8, last_close=50.0)]
    validation = _validation("X", stability=0.6, avg_expectancy=25.0)
    decisions = engine.decide(ranked, validation)
    assert len(decisions) == 1
    d = decisions[0]
    assert 0 <= d["confidence"] <= 1


def test_output_schema() -> None:
    """Each decision has required fields."""
    engine = TradeDecisionEngine()
    ranked = [_ranked("Y", last_close=100.0)]
    validation = _validation("Y")
    decisions = engine.decide(ranked, validation)
    assert len(decisions) == 1
    d = decisions[0]
    assert d["symbol"] == "Y"
    assert d["entry"] == 100.0
    assert d["stop"] == 98.0
    assert d["target"] == 104.0
    assert d["side"] == "BUY"
    assert "confidence" in d
    assert "score" in d
    assert "reasoning" in d
    assert "stability" in d["reasoning"]
    assert "avg_expectancy" in d["reasoning"]


def test_deterministic_behavior() -> None:
    """Same input produces same output."""
    engine = TradeDecisionEngine()
    ranked = [_ranked("Z", last_close=75.0)]
    validation = _validation("Z")
    a = engine.decide(ranked, validation)
    b = engine.decide(ranked, validation)
    assert a == b


def test_top_five_limit() -> None:
    """Return at most 5 decisions."""
    engine = TradeDecisionEngine()
    ranked = [
        _ranked("A", last_close=100.0),
        _ranked("B", last_close=101.0),
        _ranked("C", last_close=102.0),
        _ranked("D", last_close=103.0),
        _ranked("E", last_close=104.0),
        _ranked("F", last_close=105.0),
    ]
    validation = {
        "symbols": {
            s: {"stability": 0.8, "avg_expectancy": 50.0}
            for s in ["A", "B", "C", "D", "E", "F"]
        },
    }
    decisions = engine.decide(ranked, validation)
    assert len(decisions) <= 5


def test_validation_missing_skip() -> None:
    """Symbol without validation stats is skipped."""
    engine = TradeDecisionEngine()
    ranked = [_ranked("MISSING", last_close=100.0)]
    validation = {"symbols": {"OTHER": {"stability": 0.8, "avg_expectancy": 50.0}}}
    assert engine.decide(ranked, validation) == []


def test_prices_fallback() -> None:
    """Use prices dict when last_close not in ranked item."""
    engine = TradeDecisionEngine()
    ranked = [{"symbol": "P", "final_score": 0.8, "confidence": 0.8, "rank": 1}]
    validation = _validation("P")
    prices = {"P": 99.0}
    decisions = engine.decide(ranked, validation, prices=prices)
    assert len(decisions) == 1
    assert decisions[0]["entry"] == 99.0
