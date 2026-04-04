"""KAP alpha engine — classifier, decay, decision integration (deterministic)."""

from __future__ import annotations

import math

import pytest

from bist_core.decision.decision_engine_v2 import DecisionEngineV2, edge_bucket_key
from bist_core.features.edge_features_v2 import FeatureEngineV2
from bist_core.features.kap_classifier import classify_kap_event
from bist_core.features.kap_feature_engine import KapFeatureEngine
from bist_core.features.kap_time_decay import compute_time_decay
from bist_core.models.ohlcv import OHLCVBar
import bist_core.data.kap_fetcher as kap_fetcher_mod


def _bar(close: float, ts: int = 0) -> OHLCVBar:
    return OHLCVBar(
        symbol="ASELS",
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


def _bars_range_enter_small(n: int = 50) -> list[OHLCVBar]:
    """Low-vol chop, last near support of 20d range → institutional enter_small."""
    closes = [100.0 + (i % 4) * 0.02 + i * 0.001 for i in range(n)]
    m20 = closes[-20:]
    lo, hi = min(m20), max(m20)
    closes[-1] = lo + 0.32 * (hi - lo)
    out: list[OHLCVBar] = []
    for i, c in enumerate(closes):
        out.append(
            OHLCVBar(
                symbol="ASELS",
                open=c,
                high=c + 0.01,
                low=max(c - 0.01, 0.01),
                close=c,
                volume=1000.0,
                timestamp=i,
            )
        )
    return out


_CAP: dict[str, float] = {"capital": 100_000.0, "portfolio_exposure": 0.0}


def test_classifier_bonus_and_risk() -> None:
    now = 1_700_000_000
    r = classify_kap_event(
        {"title": "ASELS bedelsiz sermaye artırımı", "symbol": "ASELS", "timestamp": now}
    )
    assert r is not None
    assert r["event_type"] == "bonus_issue"
    assert r["strength"] == pytest.approx(1.5)

    r2 = classify_kap_event(
        {"title": "Şirket CEZA bildirimi", "symbol": "THYAO", "timestamp": now}
    )
    assert r2 is not None
    assert r2["event_type"] == "risk"
    assert r2["strength"] == pytest.approx(-1.5)


def test_classifier_no_match() -> None:
    assert (
        classify_kap_event(
            {"title": "Genel açıklama", "symbol": "X", "timestamp": 1_700_000_000}
        )
        is None
    )


def test_decay_brackets() -> None:
    t0 = 1000
    assert compute_time_decay(t0, t0 + 60) == pytest.approx(1.0)  # 1 min
    assert compute_time_decay(t0, t0 + 10 * 60) == pytest.approx(0.7)  # 10 min
    assert compute_time_decay(t0, t0 + 60 * 60) == pytest.approx(0.4)  # 60 min
    assert compute_time_decay(t0, t0 + 200 * 60) == pytest.approx(0.1)


def test_decay_invalid() -> None:
    assert compute_time_decay(-1, 100) == 0.0
    assert compute_time_decay(100, 50) == 0.0


def test_feature_engine_build() -> None:
    eng = KapFeatureEngine()
    now = 1_700_000_000
    item = {
        "title": "ASELS temettü ödemesi",
        "symbol": "ASELS",
        "timestamp": now - 120,
        "raw": "x",
    }
    f = eng.build_feature(item, now)
    assert f is not None
    assert f["symbol"] == "ASELS"
    assert f["kap_event"] == "dividend"
    assert f["kap_alpha"] > 0.0
    assert not math.isnan(f["kap_alpha"]) and not math.isnan(f["kap_age_min"])


def test_fetch_kap_rss_offline_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(kap_fetcher_mod, "network_allowed", lambda: False)
    assert kap_fetcher_mod.fetch_kap_rss() == []


def test_decision_no_kap_unchanged() -> None:
    bars = _bars_range_enter_small(50)
    fe = FeatureEngineV2()
    k = edge_bucket_key(fe.extract(bars))
    eng = DecisionEngineV2(edges={k: {"exp": 0.05, "count": 100, "confidence": 0.05}})
    px = float(bars[-1].close)
    r = eng.evaluate_symbol({"symbol": "ASELS", "current_price": px, "bars": bars, **_CAP})
    assert isinstance(r, dict)
    assert r["action"] == "enter_small"
    assert "inst_" in str(r.get("reason", ""))


def test_decision_negative_kap_no_trade() -> None:
    bars = _bars_range_enter_small(50)
    fe = FeatureEngineV2()
    k = edge_bucket_key(fe.extract(bars))
    eng = DecisionEngineV2(edges={k: {"exp": 0.05, "count": 100, "confidence": 0.05}})
    r = eng.evaluate_symbol(
        {
            "symbol": "ASELS",
            "current_price": float(bars[-1].close),
            "bars": bars,
            **_CAP,
            "kap_feature": {"kap_alpha": -0.6, "kap_event": "risk"},
        }
    )
    assert r["action"] == "hold"
    assert r["reason"] == "kap_negative"


def test_kap_boost_changes_reason_string() -> None:
    """KAP changes edge_exp in reason when edge present."""
    bars = _bars_range_enter_small(50)
    fe = FeatureEngineV2()
    k = edge_bucket_key(fe.extract(bars))
    eng = DecisionEngineV2(edges={k: {"exp": 0.05, "count": 100, "confidence": 0.05}})
    px = float(bars[-1].close)
    r0 = eng.evaluate_symbol({"symbol": "ASELS", "current_price": px, "bars": bars, **_CAP})
    r1 = eng.evaluate_symbol(
        {
            "symbol": "ASELS",
            "current_price": px,
            "bars": bars,
            **_CAP,
            "kap_feature": {"kap_alpha": 2.0, "kap_event": "bonus_issue"},
        }
    )
    assert r0["reason"] != r1["reason"]
    # KAP modulates only edge strength in reason; sizing uses confidence (unchanged).
    assert float(r0.get("position_size", 0)) == pytest.approx(float(r1.get("position_size", 0)))


__all__ = []
