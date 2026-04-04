"""Tests for DecisionEngineV2 — edge-gated, deterministic."""

from __future__ import annotations

import pytest

from bist_core.decision.decision_engine_v2 import (
    DecisionEngineV2,
    _apply_hard_edge_confidence_final,
    _apply_mtf_conflict_final,
    _brain_test,
    _strict_regime_blocks_new_entry,
    edge_bucket_key,
)
from bist_core.features.edge_features_v2 import FeatureEngineV2
from bist_core.models.ohlcv import OHLCVBar


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


def _bars_uptrend(n: int = 50) -> list[OHLCVBar]:
    closes = [50.0 + i * 2.0 for i in range(n)]
    return [_bar(c, ts=i) for i, c in enumerate(closes)]


def _bars_range_enter_small(n: int = 55) -> list[OHLCVBar]:
    """Low-vol chop with last in lower third of 20d range → RANGE / enter_small."""
    closes = [100.0 + (i % 4) * 0.02 + i * 0.001 for i in range(n)]
    m20 = closes[-20:]
    lo, hi = min(m20), max(m20)
    closes[-1] = lo + 0.32 * (hi - lo)
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


_CAP: dict[str, float] = {"capital": 100_000.0, "portfolio_exposure": 0.0}


def test_invalid_price_hold() -> None:
    eng = DecisionEngineV2()
    r = eng.evaluate_symbol({"current_price": 0, "bars": [_bar(10.0) for _ in range(50)]})
    assert isinstance(r, dict)
    assert r["action"] == "hold"
    assert r["reason"] == "invalid_price"
    assert r.get("score") == 0.0
    assert r.get("no_trade") is True


def test_insufficient_bars_hold() -> None:
    eng = DecisionEngineV2()
    r = eng.evaluate_symbol({"current_price": 100.0, "bars": [_bar(10.0) for _ in range(3)]})
    assert isinstance(r, dict)
    assert r["action"] == "hold"
    assert r["reason"] == "insufficient_bars"


def test_no_capital_institutional_hold() -> None:
    """Without capital, fail-closed before institutional sizing."""
    eng = DecisionEngineV2()
    bars = _bars_uptrend(50)
    r = eng.evaluate_symbol({"current_price": float(bars[-1].close), "bars": bars})
    assert isinstance(r, dict)
    assert r["action"] == "hold"
    assert r["reason"] == "capital_missing"


def test_nonpositive_edge_does_not_block_institutional() -> None:
    """Edge exp≤0 is ignored for single-TF; brain still evaluates (volatile uptrend → wait)."""
    bars = _bars_uptrend(50)
    fe = FeatureEngineV2()
    k = edge_bucket_key(fe.extract(bars))
    eng = DecisionEngineV2(edges={k: {"exp": 0.0, "count": 100}})
    r = eng.evaluate_symbol({"current_price": float(bars[-1].close), "bars": bars, **_CAP})
    assert isinstance(r, dict)
    assert r["action"] == "hold"
    assert str(r["reason"]).startswith("inst_wait|")
    assert r.get("no_trade") is True


def test_mtf_conflict_blocks_short_when_mtf_up() -> None:
    d = {
        "action": "enter_short",
        "symbol": "X",
        "confidence": 0.8,
        "edge_score": 0.8,
    }
    ctx = {"mtf_signal": "UP", "symbol": "X"}
    inst = {"direction": "short"}
    r = _apply_mtf_conflict_final(d, ctx, inst)
    assert r["action"] == "hold"
    assert r["reason"] == "mtf_conflict_block"


def test_mtf_conflict_blocks_long_when_mtf_down() -> None:
    d = {"action": "enter_long", "symbol": "X"}
    ctx = {"mtf_signal": "DOWN", "symbol": "X"}
    r = _apply_mtf_conflict_final(d, ctx, {"direction": "long"})
    assert r["action"] == "hold"
    assert r["reason"] == "mtf_conflict_block"


def test_mtf_explicit_enter_long_mismatch_blocks() -> None:
    d = {"action": "enter_short", "symbol": "X"}
    ctx = {"mtf_signal": "enter_long", "symbol": "X"}
    r = _apply_mtf_conflict_final(d, ctx, {"direction": "short"})
    assert r["reason"] == "mtf_conflict_block"


def test_mtf_aligned_enter_long_passes() -> None:
    d = {"action": "enter_long", "position_size": 100.0}
    ctx = {"mtf_signal": "UP", "symbol": "X"}
    r = _apply_mtf_conflict_final(d, ctx, {"direction": "long"})
    assert r["action"] == "enter_long"
    assert float(r.get("position_size", 0.0)) == 100.0


def test_hard_edge_confidence_final_blocks_low_edge() -> None:
    d = {
        "action": "enter_long",
        "edge_score": 0.5,
        "confidence": 0.9,
        "reason": "x",
    }
    r = _apply_hard_edge_confidence_final(d, symbol="Z")
    assert r["action"] == "hold"
    assert "hard_edge_below_0_60" in str(r["reason"])


def test_hard_edge_confidence_final_blocks_low_confidence() -> None:
    d = {
        "action": "enter_long",
        "edge_score": 0.9,
        "confidence": 0.5,
        "reason": "x",
    }
    r = _apply_hard_edge_confidence_final(d, symbol="Z")
    assert r["action"] == "hold"
    assert "hard_confidence_below_0_55" in str(r["reason"])


def test_hard_edge_confidence_final_passes_at_thresholds() -> None:
    d = {
        "action": "enter_long",
        "edge_score": 0.6,
        "confidence": 0.55,
        "reason": "x",
        "position_size": 100.0,
    }
    r = _apply_hard_edge_confidence_final(d, symbol="Z")
    assert r["action"] == "enter_long"
    assert float(r.get("position_size", 0.0)) == 100.0


def test_strict_regime_range_gate_table() -> None:
    assert not _strict_regime_blocks_new_entry("RANGE", 0.75, 1)
    assert not _strict_regime_blocks_new_entry("RANGE", 1.0, 1)
    assert _strict_regime_blocks_new_entry("RANGE", 0.749999, 1)
    assert _strict_regime_blocks_new_entry("RANGE", 0.75, 0)
    assert not _strict_regime_blocks_new_entry("TRENDING_UP", 0.1, 0)
    assert not _strict_regime_blocks_new_entry("VOLATILE", 0.0, 0)


def test_range_regime_blocks_entry_without_exception() -> None:
    """RANGE + edge below strict 0.75 breakout gate → hold (or inst hold if edge < 0.60)."""
    bars = _bars_range_enter_small(55)
    fe = FeatureEngineV2()
    k = edge_bucket_key(fe.extract(bars))
    eng = DecisionEngineV2(edges={k: {"exp": 0.015, "count": 100, "confidence": 0.05}})
    px = float(bars[-1].close)
    r = eng.evaluate_symbol(
        {
            "symbol": "X",
            "current_price": px,
            "bars": bars,
            **_CAP,
            "mtf_signal": "UP",
        }
    )
    assert isinstance(r, dict)
    assert r["action"] == "hold"
    assert r.get("no_trade") is True
    assert r.get("market_state") == "RANGE"
    assert (
        r["reason"] == "EDGE_BELOW_THRESHOLD"
        or r["reason"] == "strict_regime_range"
        or str(r["reason"]).startswith("inst_hold|RANGE|")
    )


def test_non_range_regime_does_not_apply_strict_range_hold() -> None:
    """VOLATILE/TREND/NEUTRAL paths must not return strict_regime_range (filter is RANGE-only)."""
    bars = _bars_uptrend(55)
    fe = FeatureEngineV2()
    k = edge_bucket_key(fe.extract(bars))
    eng = DecisionEngineV2(edges={k: {"exp": 0.015, "count": 100, "confidence": 0.05}})
    px = float(bars[-1].close)
    r = eng.evaluate_symbol(
        {
            "symbol": "X",
            "current_price": px,
            "bars": bars,
            **_CAP,
            "mtf_signal": "UP",
        }
    )
    assert isinstance(r, dict)
    assert r.get("market_state") != "RANGE"
    assert r.get("reason") != "strict_regime_range"


def test_score_in_unit_interval_when_edge() -> None:
    bars = _bars_uptrend(50)
    fe = FeatureEngineV2()
    k = edge_bucket_key(fe.extract(bars))
    eng = DecisionEngineV2(edges={k: {"exp": 0.5, "count": 80, "confidence": 0.5}})
    px = float(bars[-1].close) * 0.88
    r = eng.evaluate_symbol({"current_price": px, "bars": bars, **_CAP})
    assert r is not None
    assert "score" in r
    assert -1.0 <= float(r["score"]) <= 1.0


def test_lookback_clamped_to_default() -> None:
    eng = DecisionEngineV2(lookback=3)
    assert eng._lookback == 20


def test_low_edge_confidence_still_institutional_volatile_wait() -> None:
    """Low edge confidence no longer gates single-TF; volatile path → wait/hold."""
    bars = _bars_uptrend(50)
    fe = FeatureEngineV2()
    k = edge_bucket_key(fe.extract(bars))
    eng = DecisionEngineV2(edges={k: {"exp": 0.04, "count": 100, "confidence": 0.015}})
    px = float(bars[-1].close) * 0.88
    r = eng.evaluate_symbol({"symbol": "X", "current_price": px, "bars": bars, **_CAP})
    assert isinstance(r, dict)
    assert r["action"] == "hold"
    assert str(r["reason"]).startswith("inst_wait|")


def test_missing_capital_no_trade() -> None:
    bars = _bars_uptrend(50)
    fe = FeatureEngineV2()
    k = edge_bucket_key(fe.extract(bars))
    eng = DecisionEngineV2(edges={k: {"exp": 0.05, "count": 100, "confidence": 0.05}})
    r = eng.evaluate_symbol({"symbol": "X", "current_price": float(bars[-1].close), "bars": bars})
    assert isinstance(r, dict)
    assert r["action"] == "hold"
    assert r["reason"] == "capital_missing"


def test_edge_store_load_via_constructor() -> None:
    bars = _bars_uptrend(50)
    fe = FeatureEngineV2()
    k = edge_bucket_key(fe.extract(bars))
    m = {k: {"exp": 0.01, "count": 50}}
    eng = DecisionEngineV2(edges=m)
    assert eng.edge_store.get(k) == {"exp": 0.01, "count": 50}


def test_brain_harness_scores_actions_rationale_differ() -> None:
    out = _brain_test()
    assert set(out.keys()) == {"ASELS", "THYAO", "SISE"}
    scores = [float(out[s]["score"]) for s in out]
    assert len(set(scores)) == 3
    actions = [str(out[s]["action"]) for s in out]
    assert len(set(actions)) == 3
    reasons = [str(out[s]["reason"]) for s in out]
    assert len(set(reasons)) == 3
