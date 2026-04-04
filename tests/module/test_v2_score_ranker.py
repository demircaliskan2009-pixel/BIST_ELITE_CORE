"""Tests for ScoreRanker (DecisionEngineV2 scores) — deterministic."""

from __future__ import annotations

from bist_core.decision.decision_engine_v2 import DecisionEngineV2, edge_bucket_key
from bist_core.features.edge_features_v2 import FeatureEngineV2
from bist_core.models.ohlcv import OHLCVBar
from bist_core.rank.v2_score_ranker import ScoreRanker


def _bar(close: float, ts: int = 0) -> OHLCVBar:
    return OHLCVBar(
        symbol="X",
        open=close,
        high=close + 0.5,
        low=max(close - 0.5, 0.01),
        close=close,
        volume=1000.0,
        timestamp=ts,
    )


def _bars(closes: list[float]) -> list[OHLCVBar]:
    return [_bar(c, ts=i) for i, c in enumerate(closes)]


def _bars_tight(closes: list[float]) -> list[OHLCVBar]:
    """Narrow high/low so institutional path stays low-vol (RANGE), not VOLATILE."""
    return [
        OHLCVBar(
            symbol="X",
            open=c,
            high=c + 0.01,
            low=max(c - 0.01, 0.01),
            close=c,
            volume=1000.0,
            timestamp=i,
        )
        for i, c in enumerate(closes)
    ]


def _closes_range_enter_small(n: int = 50) -> list[float]:
    closes = [100.0 + (i % 4) * 0.02 + i * 0.001 for i in range(n)]
    m20 = closes[-20:]
    lo, hi = min(m20), max(m20)
    closes[-1] = lo + 0.32 * (hi - lo)
    return closes


def _ctx_range_enter_small() -> dict:
    closes = _closes_range_enter_small(50)
    bars = _bars_tight(closes)
    return {
        "current_price": closes[-1],
        "bars": bars,
        "capital": 100_000.0,
        "portfolio_exposure": 0.0,
    }


def _ctx_uptrend() -> dict:
    closes = [50.0 + i * 2.0 for i in range(50)]
    bars = _bars(closes)
    return {
        "current_price": closes[-1],
        "bars": bars,
        "capital": 100_000.0,
        "portfolio_exposure": 0.0,
    }


def _ctx_downtrend() -> dict:
    closes = [200.0 - i * 3.0 for i in range(50)]
    bars = _bars(closes)
    return {
        "current_price": closes[-1],
        "bars": bars,
        "capital": 100_000.0,
        "portfolio_exposure": 0.0,
    }


def _engine_two_series() -> DecisionEngineV2:
    fe = FeatureEngineV2()
    bu = _bars_tight(_closes_range_enter_small(50))
    bd = _bars([200.0 - i * 3.0 for i in range(50)])
    ku = edge_bucket_key(fe.extract(bu))
    kd = edge_bucket_key(fe.extract(bd))
    return DecisionEngineV2(
        edges={
            ku: {"exp": 0.08, "count": 100},
            kd: {"exp": 0.03, "count": 100},
        }
    )


def test_rank_empty() -> None:
    r = ScoreRanker().rank({})
    assert r == []


def test_rank_deterministic_order_and_scores() -> None:
    eng = _engine_two_series()
    sr = ScoreRanker(engine=eng)
    cu = _ctx_uptrend()
    cu["current_price"] = float(cu["bars"][-1].close) * 0.88
    out = sr.rank(
        {
            "ZZ": _ctx_downtrend(),
            "AA": cu,
        }
    )
    assert len(out) == 2
    assert out[0]["rank"] == 1
    assert out[1]["rank"] == 2
    assert out[0]["symbol"] == "AA"
    assert out[1]["symbol"] == "ZZ"
    assert -1.0 <= out[0]["score"] <= 1.0
    assert -1.0 <= out[1]["score"] <= 1.0
    assert out[0]["score"] >= out[1]["score"]
    assert "decision" in out[0]
    assert out[0]["decision"].get("score") == out[0]["score"]


def test_rank_top_n() -> None:
    fe = FeatureEngineV2()
    b1 = _bars([50.0 + i * 2.0 for i in range(50)])
    b2 = _bars([200.0 - i * 3.0 for i in range(50)])
    b3 = _bars([55.0 + i * 1.5 for i in range(50)])
    k1 = edge_bucket_key(fe.extract(b1))
    k2 = edge_bucket_key(fe.extract(b2))
    k3 = edge_bucket_key(fe.extract(b3))
    eng = DecisionEngineV2(
        edges={
            k1: {"exp": 0.09, "count": 100, "confidence": 0.09},
            k2: {"exp": 0.02, "count": 100, "confidence": 0.02},
            k3: {"exp": 0.05, "count": 100, "confidence": 0.05},
        }
    )
    sr = ScoreRanker(engine=eng)
    cap = {"capital": 100_000.0, "portfolio_exposure": 0.0}
    out = sr.rank(
        {
            "A": {"current_price": b1[-1].close, "bars": b1, **cap},
            "B": {"current_price": b2[-1].close, "bars": b2, **cap},
            "C": {"current_price": b3[-1].close, "bars": b3, **cap},
        },
        top_n=2,
    )
    assert len(out) == 2
    assert out[0]["rank"] == 1
    assert out[1]["rank"] == 2


def test_rank_skips_bad_context() -> None:
    fe = FeatureEngineV2()
    b = _bars([50.0 + i * 2.0 for i in range(50)])
    k = edge_bucket_key(fe.extract(b))
    eng = DecisionEngineV2(edges={k: {"exp": 0.05, "count": 100, "confidence": 0.05}})
    sr = ScoreRanker(engine=eng)
    out = sr.rank(
        {
            "X": "not_a_dict",
            "Y": {
                "current_price": b[-1].close,
                "bars": b,
                "capital": 100_000.0,
                "portfolio_exposure": 0.0,
            },
        }
    )
    assert len(out) == 1
    assert out[0]["symbol"] == "Y"


def test_enter_actions_when_edge_loaded() -> None:
    eng = _engine_two_series()
    sr = ScoreRanker(engine=eng)
    out = sr.rank(
        {
            "LONG": _ctx_range_enter_small(),
            "SHORT": _ctx_downtrend(),
        }
    )
    by_sym = {r["symbol"]: r for r in out}
    assert by_sym["LONG"]["action"] == "enter_small"
    assert by_sym["SHORT"]["action"] == "hold"
