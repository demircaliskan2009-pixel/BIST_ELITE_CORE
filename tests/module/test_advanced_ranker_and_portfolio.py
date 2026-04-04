"""AdvancedRanker + inverse-vol PortfolioEngine — deterministic."""

from __future__ import annotations

from bist_core.decision.decision_engine_v2 import DecisionEngineV2, edge_bucket_key
from bist_core.features.edge_features_v2 import FeatureEngineV2
from bist_core.models.ohlcv import OHLCVBar
from bist_core.portfolio.portfolio_engine import PortfolioEngine
from bist_core.rank.advanced_ranker import AdvancedRanker


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


def _engine_for_ctx_pair(bars_a: list[OHLCVBar], bars_b: list[OHLCVBar]) -> DecisionEngineV2:
    fe = FeatureEngineV2()
    ka = edge_bucket_key(fe.extract(bars_a))
    kb = edge_bucket_key(fe.extract(bars_b))
    return DecisionEngineV2(
        edges={
            ka: {"exp": 0.07, "count": 100, "confidence": 0.07},
            kb: {"exp": 0.06, "count": 100, "confidence": 0.06},
        }
    )


def test_weights_sum_to_one() -> None:
    closes_a = [50.0 + i * 2.0 for i in range(50)]
    closes_b = [100.0 + i * 0.1 for i in range(50)]
    bars_a = [_bar(c, ts=i) for i, c in enumerate(closes_a)]
    bars_b = [_bar(c, ts=i) for i, c in enumerate(closes_b)]
    eng = _engine_for_ctx_pair(bars_a, bars_b)
    cap = {"capital": 100_000.0, "portfolio_exposure": 0.0}
    ctx = {
        "A": {"current_price": closes_a[-1], "bars": bars_a, **cap},
        "B": {"current_price": closes_b[-1], "bars": bars_b, **cap},
    }
    ranked = AdvancedRanker(engine=eng).rank(ctx)
    out = PortfolioEngine(top_n=5).allocate(ranked)
    assert len(out) >= 1
    s = sum(p["weight"] for p in out)
    assert abs(s - 1.0) < 1e-9


def test_lower_volatility_higher_weight() -> None:
    """Two symbols: higher vol → lower weight (inverse-vol)."""
    low_vol = [100.0 + i * 0.01 for i in range(50)]
    high_vol = [100.0 + (i % 3) * 5.0 for i in range(50)]
    bars_lo = [_bar(c, ts=i) for i, c in enumerate(low_vol)]
    bars_hi = [_bar(c, ts=i) for i, c in enumerate(high_vol)]
    eng = _engine_for_ctx_pair(bars_lo, bars_hi)
    cap = {"capital": 100_000.0, "portfolio_exposure": 0.0}
    ctx = {
        "LOWV": {"current_price": low_vol[-1], "bars": bars_lo, **cap},
        "HIGHV": {"current_price": high_vol[-1], "bars": bars_hi, **cap},
    }
    ranked = AdvancedRanker(engine=eng).rank(ctx)
    w = {p["symbol"]: p["weight"] for p in PortfolioEngine(top_n=2).allocate(ranked)}
    assert w["LOWV"] > w["HIGHV"]


def test_deterministic_rank_and_weights() -> None:
    closes = [50.0 + i * 2.0 for i in range(50)]
    bars = [_bar(c, ts=i) for i, c in enumerate(closes)]
    fe = FeatureEngineV2()
    k = edge_bucket_key(fe.extract(bars))
    eng = DecisionEngineV2(edges={k: {"exp": 0.05, "count": 100, "confidence": 0.05}})
    cap = {"capital": 100_000.0, "portfolio_exposure": 0.0}
    ctx = {"G": {"current_price": closes[-1], "bars": bars, **cap}}
    r1 = AdvancedRanker(engine=eng).rank(ctx)
    r2 = AdvancedRanker(engine=eng).rank(ctx)
    assert r1 == r2
    p1 = PortfolioEngine().allocate(r1)
    p2 = PortfolioEngine().allocate(r2)
    assert p1 == p2


def test_single_symbol_weight_capped() -> None:
    closes = [50.0 + i * 2.0 for i in range(50)]
    bars = [_bar(c, ts=i) for i, c in enumerate(closes)]
    fe = FeatureEngineV2()
    k = edge_bucket_key(fe.extract(bars))
    eng = DecisionEngineV2(edges={k: {"exp": 0.05, "count": 100, "confidence": 0.05}})
    cap = {"capital": 100_000.0, "portfolio_exposure": 0.0}
    ctx = {"G": {"current_price": closes[-1], "bars": bars, **cap}}
    ranked = AdvancedRanker(engine=eng).rank(ctx)
    out = PortfolioEngine(top_n=5).allocate(ranked)
    assert len(out) == 1
    assert abs(out[0]["weight"] - 1.0) < 1e-9


def test_all_zero_vol_equal_weights() -> None:
    ranked = [
        {"symbol": "A", "rank_score": 1.0, "volatility": 0.0, "returns": 0.0, "score": 0.5},
        {"symbol": "B", "rank_score": 0.9, "volatility": 0.0, "returns": 0.0, "score": 0.5},
    ]
    out = PortfolioEngine(top_n=5).allocate(ranked)
    assert len(out) == 2
    assert abs(out[0]["weight"] - 0.5) < 1e-9
    assert abs(out[1]["weight"] - 0.5) < 1e-9
