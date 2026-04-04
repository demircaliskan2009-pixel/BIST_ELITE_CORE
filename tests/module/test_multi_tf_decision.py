"""DecisionEngineV2 multi-TF fusion."""

from __future__ import annotations

from bist_core.decision.decision_engine_v2 import DecisionEngineV2, edge_bucket_key
from bist_core.features.edge_features_v2 import FeatureEngineV2
from bist_core.models.ohlcv import OHLCVBar


def _bars(n: int, sym: str = "ASELS") -> list[OHLCVBar]:
    out: list[OHLCVBar] = []
    for i in range(n):
        c = 100.0 + i * 0.02
        out.append(
            OHLCVBar(
                timestamp=1_700_000_000 + i * 60,
                symbol=sym,
                open=c,
                high=c + 0.3,
                low=c - 0.3,
                close=c,
                volume=1_000_000.0,
            )
        )
    return out


def test_multi_tf_none_without_consensus() -> None:
    b = _bars(50)
    fe = FeatureEngineV2()
    k = edge_bucket_key(fe.extract(b))
    edges_by_tf = {
        "1m": {k: {"exp": 0.02, "count": 50}},
    }
    eng = DecisionEngineV2(edges_by_tf=edges_by_tf)
    r = eng.evaluate_symbol(
        {
            "symbol": "ASELS",
            "current_price": float(b[-1].close),
            "multi_tf": {"1m": b},
        }
    )
    assert isinstance(r, dict)
    assert r["action"] == "hold"
    assert r["reason"] == "multi_tf_no_consensus"


def test_multi_tf_enter_with_two_tf() -> None:
    b1 = _bars(50)
    b2 = _bars(50)
    fe = FeatureEngineV2()
    k1 = edge_bucket_key(fe.extract(b1))
    k2 = edge_bucket_key(fe.extract(b2))
    edges_by_tf = {
        "1m": {k1: {"exp": 0.04, "count": 50}},
        "5m": {k2: {"exp": 0.06, "count": 50}},
    }
    eng = DecisionEngineV2(edges_by_tf=edges_by_tf)
    r = eng.evaluate_symbol(
        {
            "symbol": "ASELS",
            "current_price": float(b1[-1].close),
            "multi_tf": {"1m": b1, "5m": b2},
            "capital": 100_000.0,
            "portfolio_exposure": 0.0,
        }
    )
    assert isinstance(r, dict)
    assert r["action"] == "enter"
    assert r["reason"] == "MULTI_EDGE_2"
    assert r["strategy"] == "multi_edge"
    assert 0.2 <= float(r["confidence"]) <= 0.9
    assert str(r.get("edge_signal") or "") in (
        "STRONG_BUY",
        "BUY",
        "SELL",
        "STRONG_SELL",
    )
