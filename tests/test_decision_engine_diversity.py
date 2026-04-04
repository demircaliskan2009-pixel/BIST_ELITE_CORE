"""DecisionEngineV2 — distinct bar paths must yield distinct composite scores."""

from __future__ import annotations

from bist_core.decision.decision_engine_v2 import DecisionEngineV2, edge_bucket_key, run_sample_test
from bist_core.features.edge_features_v2 import FeatureEngineV2
from bist_core.models.ohlcv import OHLCVBar


def _bars_for_symbol(symbol: str, start: float, slope: float, n: int = 50) -> list[OHLCVBar]:
    out: list[OHLCVBar] = []
    for i in range(n):
        c = start + float(i) * slope
        out.append(
            OHLCVBar(
                timestamp=i,
                symbol=symbol,
                open=c,
                high=c + 0.5,
                low=max(c - 0.5, 0.01),
                close=c,
                volume=1000.0 + float(i),
            )
        )
    return out


def test_three_symbols_scores_not_identical() -> None:
    cap = {"capital": 100_000.0, "portfolio_exposure": 0.0}
    fe = FeatureEngineV2()
    specs = [
        ("AAA", 10.0, 0.6),
        ("BBB", 200.0, 6.0),
        ("CCC", 3.0, 0.08),
    ]
    edges: dict = {}
    for sym, st, sl in specs:
        bars = _bars_for_symbol(sym, st, sl)
        k = edge_bucket_key(fe.extract(bars))
        edges[k] = {"exp": 0.02, "count": 100, "confidence": 0.06}
    eng = DecisionEngineV2(edges=edges)
    scores: list[float] = []
    for sym, st, sl in specs:
        bars = _bars_for_symbol(sym, st, sl)
        px = float(bars[-1].close) * 0.88
        r = eng.evaluate_symbol({"symbol": sym, "current_price": px, "bars": bars, **cap})
        scores.append(float(r["score"]))
    assert len(set(round(s, 6) for s in scores)) >= 2


def test_run_sample_test_reports_diversity() -> None:
    out = run_sample_test()
    assert out["diverse"] is True
    assert out["unique_score_count"] >= 2
