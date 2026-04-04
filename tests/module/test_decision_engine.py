"""Tests for Decision Engine — trade decisions from ranked candidates and context."""

from __future__ import annotations

import pytest

from bist_core.models.ohlcv import OHLCVBar
from bist_core.scan import AdaptiveScanEngine, Scanner
from bist_core.rank import Ranker
from bist_core.decision import ContextBuilder, DecisionEngine
from bist_core.regime import TRENDING_DOWN, TRENDING_UP


def _bar(
    ts: str,
    close: float,
    volume: float = 1000.0,
    high: float | None = None,
    low: float | None = None,
) -> OHLCVBar:
    h = high if high is not None else close + 1
    lo = low if low is not None else max(close - 1, 0.01)
    return OHLCVBar(timestamp=ts, symbol="X", open=close, high=h, low=lo, close=close, volume=volume)


def test_buy_decision() -> None:
    """Score > threshold AND score_modifier >= 1.0 AND regime TRENDING_UP → BUY."""
    engine = DecisionEngine(threshold=1.0)
    candidate = {"symbol": "GARAN", "score": 5.0, "score_modifier": 1.0, "reasons": {}}
    context = {"current_price": 100.0, "trend": 5.0, "avg_range": 2.0, "regime": TRENDING_UP}
    d = engine.decide(candidate, context)
    assert d["action"] == "BUY"
    assert d["entry"] == 100.0
    assert d["stop"] == 98.0
    assert d["target"] == 103.0
    assert d["confidence"] == 0.5


def test_no_trade_low_score() -> None:
    """Score <= threshold → NO_TRADE."""
    engine = DecisionEngine(threshold=10.0)
    candidate = {"symbol": "GARAN", "score": 5.0, "score_modifier": 1.0, "reasons": {}}
    context = {"current_price": 100.0, "trend": 5.0, "avg_range": 2.0}
    d = engine.decide(candidate, context)
    assert d["action"] == "NO_TRADE"


def test_no_trade_weak_signal() -> None:
    """score < threshold * 1.2 → NO_TRADE (weak signal filter)."""
    engine = DecisionEngine(threshold=1.0)
    candidate = {"symbol": "GARAN", "score": 1.1, "score_modifier": 1.0, "reasons": {}}
    context = {"current_price": 100.0, "trend": 5.0, "avg_range": 2.0}
    d = engine.decide(candidate, context)
    assert d["action"] == "NO_TRADE"


def test_no_trade_low_score_modifier() -> None:
    """score_modifier < 1.0 (failed filter) → NO_TRADE."""
    engine = DecisionEngine(threshold=0.0)
    candidate = {"symbol": "GARAN", "score": 5.0, "score_modifier": 0.0, "reasons": {}}
    context = {"current_price": 100.0, "trend": 5.0, "avg_range": 2.0}
    d = engine.decide(candidate, context)
    assert d["action"] == "NO_TRADE"


def test_buy_allowed_with_negative_trend() -> None:
    """Score > threshold AND score_modifier >= 1.0 AND regime TRENDING_UP → BUY."""
    engine = DecisionEngine(threshold=1.0)
    candidate = {"symbol": "GARAN", "score": 5.0, "score_modifier": 1.0, "reasons": {}}
    context = {"current_price": 100.0, "trend": -1.0, "avg_range": 2.0, "regime": TRENDING_UP}
    d = engine.decide(candidate, context)
    assert d["action"] == "BUY"


def test_no_trade_trending_down_regime() -> None:
    """TRENDING_DOWN regime → NO_TRADE regardless of score."""
    engine = DecisionEngine(threshold=0.0)
    candidate = {"symbol": "GARAN", "score": 10.0, "score_modifier": 1.0, "reasons": {}}
    context = {"current_price": 100.0, "trend": -5.0, "avg_range": 2.0, "regime": TRENDING_DOWN}
    d = engine.decide(candidate, context)
    assert d["action"] == "NO_TRADE"


def test_no_trade_low_avg_range() -> None:
    """avg_range < 0.5% of price → NO_TRADE."""
    engine = DecisionEngine(threshold=0.0)
    candidate = {"symbol": "X", "score": 5.0, "score_modifier": 1.0, "reasons": {}}
    context = {"current_price": 100.0, "trend": 5.0, "avg_range": 0.001}
    d = engine.decide(candidate, context)
    assert d["action"] == "NO_TRADE"


def test_invalid_input_fail_closed() -> None:
    """Missing fields → NO_TRADE."""
    engine = DecisionEngine(threshold=1.0)
    candidate = {"symbol": "X"}
    context = {"current_price": 100.0, "trend": 5.0, "avg_range": 2.0}
    d = engine.decide(candidate, context)
    assert d["action"] == "NO_TRADE"

    candidate2 = {"symbol": "X", "score": 5.0, "reasons": {}}
    context2 = {}
    d2 = engine.decide(candidate2, context2)
    assert d2["action"] == "NO_TRADE"


def test_determinism() -> None:
    """Same input produces same output."""
    engine = DecisionEngine(threshold=1.0)
    candidate = {"symbol": "GARAN", "score": 5.0, "score_modifier": 1.0, "reasons": {}}
    context = {"current_price": 100.0, "trend": 5.0, "avg_range": 2.0, "regime": TRENDING_UP}
    a = engine.decide(candidate, context)
    b = engine.decide(candidate, context)
    assert a == b


def test_stop_target_logic() -> None:
    """stop = entry - avg_range, target = entry + (avg_range * 1.5)."""
    engine = DecisionEngine(threshold=0.0)
    candidate = {"symbol": "X", "score": 1.0, "score_modifier": 1.0, "reasons": {}}
    context = {"current_price": 50.0, "trend": 1.0, "avg_range": 5.0, "regime": TRENDING_UP}
    d = engine.decide(candidate, context)
    assert d["action"] == "BUY"
    assert d["entry"] == 50.0
    assert d["stop"] == 45.0
    assert d["target"] == 57.5


def test_full_pipeline_integration() -> None:
    """Scanner → Ranker → ContextBuilder → DecisionEngine."""
    bars_by_symbol: dict[str, list[OHLCVBar]] = {
        "GARAN": [
            _bar("1704067200", 98.0, 5000),
            _bar("1704153600", 100.0, 6000),
            _bar("1704240000", 102.0, 7000),
        ],
        "ASELS": [
            _bar("1704067200", 50.0, 3000),
            _bar("1704153600", 48.0, 2500),
            _bar("1704240000", 46.0, 2000),
        ],
    }

    def loader(symbol: str) -> list[OHLCVBar]:
        return bars_by_symbol.get(symbol, [])

    scanner = Scanner(loader, ["GARAN", "ASELS"], AdaptiveScanEngine())
    candidates = scanner.scan()
    assert len(candidates) == 2

    ranker = Ranker({"momentum": 0.5, "volatility": 0.5})
    ranked = ranker.rank(candidates, top_n=5)
    assert len(ranked) == 2

    ctx_builder = ContextBuilder()
    engine = DecisionEngine(threshold=1.0)

    decisions = []
    for r in ranked:
        symbol = r["symbol"]
        bars = bars_by_symbol[symbol]
        context = ctx_builder.build(bars)
        dec = engine.decide(r, context)
        decisions.append(dec)

    garan_dec = next(d for d in decisions if d["symbol"] == "GARAN")
    asels_dec = next(d for d in decisions if d["symbol"] == "ASELS")

    assert garan_dec["action"] == "BUY"
    assert garan_dec["entry"] == 102.0
    assert garan_dec["stop"] < garan_dec["entry"]
    assert garan_dec["target"] > garan_dec["entry"]
    assert asels_dec["action"] == "NO_TRADE"


def test_context_builder() -> None:
    """ContextBuilder produces correct schema including regime."""
    bars = [
        _bar("1704067200", 100.0),
        _bar("1704153600", 102.0),
    ]
    ctx = ContextBuilder().build(bars)
    assert ctx["current_price"] == 102.0
    assert ctx["trend"] == 2.0
    assert ctx["avg_range"] == 2.0
    assert "regime" in ctx
    assert ctx["regime"] in ("TRENDING_UP", "TRENDING_DOWN", "RANGE", "HIGH_VOLATILITY", "UNKNOWN")


def test_context_builder_invalid_raises() -> None:
    """ContextBuilder raises on invalid bars."""
    from bist_core.data.quality import InvalidDataError

    with pytest.raises(InvalidDataError):
        ContextBuilder().build([])


# ---------------------------------------------------------------------------
# TradeDecisionEngine — ranked + validation → trade decisions
# ---------------------------------------------------------------------------

def _ranked(symbol: str, final_score: float = 0.8, last_close: float = 100.0) -> dict:
    return {"symbol": symbol, "final_score": final_score, "confidence": final_score, "rank": 1, "last_close": last_close}


def _validation(symbol: str, stability: float = 0.7, avg_expectancy: float = 50.0) -> dict:
    return {"symbols": {symbol: {"windows": [], "avg_expectancy": avg_expectancy, "avg_drawdown": 0.05, "stability": stability}}}


def test_trade_decision_filtering() -> None:
    """TradeDecisionEngine skips only when stability < 0."""
    from bist_core.decision import TradeDecisionEngine

    engine = TradeDecisionEngine()
    ranked = [_ranked("A", last_close=100.0)]
    assert engine.decide(ranked, {"symbols": {"A": {"stability": -0.1, "avg_expectancy": 50.0}}}) == []
    assert len(engine.decide(ranked, {"symbols": {"A": {"stability": 0.3, "avg_expectancy": 50.0}}})) == 1
    assert len(engine.decide(ranked, {"symbols": {"A": {"stability": 0.7, "avg_expectancy": 0.0}}})) == 1


def test_trade_decision_output_schema() -> None:
    """TradeDecisionEngine produces valid decision schema."""
    from bist_core.decision import TradeDecisionEngine

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
    assert "reasoning" in d


def test_trade_decision_deterministic() -> None:
    """TradeDecisionEngine is deterministic."""
    from bist_core.decision import TradeDecisionEngine

    engine = TradeDecisionEngine()
    ranked = [_ranked("Z", last_close=75.0)]
    validation = _validation("Z")
    assert engine.decide(ranked, validation) == engine.decide(ranked, validation)
