"""Tests for Current Context Analyzer — entry status classification."""

from __future__ import annotations

from bist_core.context import CurrentContextAnalyzer


def _decision(symbol: str, entry: float = 100.0) -> dict:
    return {"symbol": symbol, "entry": entry, "stop": 98.0, "target": 104.0}


def test_context_classification() -> None:
    """Correct status for delta thresholds."""
    analyzer = CurrentContextAnalyzer()

    d_missed = _decision("A", entry=100.0)
    out = analyzer.analyze([d_missed], {"A": 104.0})
    assert len(out) == 1
    assert out[0]["entry_status"] == "missed_entry"
    assert out[0]["entry_delta"] == 0.04

    d_late = _decision("B", entry=100.0)
    out = analyzer.analyze([d_late], {"B": 102.0})
    assert len(out) == 1
    assert out[0]["entry_status"] == "late_entry"

    d_ideal = _decision("C", entry=100.0)
    out = analyzer.analyze([d_ideal], {"C": 100.0})
    assert len(out) == 1
    assert out[0]["entry_status"] == "ideal_entry"

    d_ideal_neg = _decision("D", entry=100.0)
    out = analyzer.analyze([d_ideal_neg], {"D": 99.0})
    assert len(out) == 1
    assert out[0]["entry_status"] == "ideal_entry"

    d_pullback = _decision("E", entry=100.0)
    out = analyzer.analyze([d_pullback], {"E": 97.0})
    assert len(out) == 1
    assert out[0]["entry_status"] == "pullback"


def test_missing_price_handling() -> None:
    """Symbol without price is skipped."""
    analyzer = CurrentContextAnalyzer()
    decisions = [_decision("A"), _decision("B")]
    prices = {"A": 100.0}
    out = analyzer.analyze(decisions, prices)
    assert len(out) == 1
    assert out[0]["symbol"] == "A"


def test_boundary_values() -> None:
    """Boundary deltas classified correctly."""
    analyzer = CurrentContextAnalyzer()
    d = _decision("X", entry=100.0)
    assert analyzer.analyze([d], {"X": 103.0})[0]["entry_status"] == "late_entry"
    assert analyzer.analyze([d], {"X": 103.01})[0]["entry_status"] == "missed_entry"
    assert analyzer.analyze([d], {"X": 98.0})[0]["entry_status"] == "ideal_entry"
    assert analyzer.analyze([d], {"X": 97.99})[0]["entry_status"] == "pullback"
