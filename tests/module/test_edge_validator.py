"""EdgeValidator — dual-source decision comparison (no crash)."""

from __future__ import annotations

from bist_core.analysis.edge_validator import EdgeValidator
from bist_core.decision.decision_engine_v2 import DecisionEngineV2
from bist_core.models.ohlcv import OHLCVBar


def _bar(ts: int, close: float, sym: str = "X") -> OHLCVBar:
    return OHLCVBar(
        timestamp=ts,
        symbol=sym,
        open=close,
        high=close + 0.1,
        low=max(close - 0.1, 0.01),
        close=close,
        volume=1000.0,
    )


def test_compare_empty_lists() -> None:
    ev = EdgeValidator()
    eng = DecisionEngineV2()
    r = ev.compare("ASELS", [], [], eng)
    assert r["symbol"] == "ASELS"
    assert r["ideal_decision"] is None
    assert r["matriks_decision"] is None


def test_compare_never_raises() -> None:
    ev = EdgeValidator()
    eng = DecisionEngineV2()
    bars = [_bar(i, 50.0 + i * 0.01) for i in range(50)]
    r = ev.compare("ASELS", bars, bars, eng)
    assert isinstance(r, dict)
    assert "ideal_decision" in r and "matriks_decision" in r
