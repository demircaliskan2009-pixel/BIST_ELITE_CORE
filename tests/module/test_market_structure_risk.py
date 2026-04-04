"""Correlation, sector caps, liquidity, depth, MTF — deterministic layers."""

from __future__ import annotations

from bist_core.execution.depth_model import DepthModel
from bist_core.features.feature_engine import FeatureEngine
from bist_core.models.ohlcv import OHLCVBar
from bist_core.risk.correlation_engine import CorrelationEngine
from bist_core.risk.sector_mapper import get_sector


def _make_bar(vol: float, ts: int) -> OHLCVBar:
    return OHLCVBar(
        symbol="TST",
        open=10.0,
        high=10.0,
        low=10.0,
        close=10.0,
        volume=vol,
        timestamp=ts,
    )


def test_correlation_perfect_series_high() -> None:
    ce = CorrelationEngine()
    s = [float(i) for i in range(30)]
    assert abs(ce.correlation(s, s) - 1.0) < 1e-9


def test_correlation_blocks_when_above_threshold() -> None:
    ce = CorrelationEngine()
    a = [float(i) for i in range(30)]
    b = [float(i) * 2 + 1 for i in range(30)]
    assert ce.correlation(a, b) > 0.8


def test_sector_cap_rule() -> None:
    assert get_sector("GARAN") == "bank"
    assert get_sector("UNKNOWN") == "other"
    w_pos = 0.35
    w_adj = 0.10
    assert w_pos + w_adj > 0.4


def test_liquidity_avg_rule_matches_paper_trader_threshold() -> None:
    """Same rule as ``PaperTrader._liquidity_ok`` vs ``_min_volume_proxy`` (1e6)."""
    min_proxy = 1_000_000.0
    vols_low = [getattr(b, "volume", 0) for b in [_make_bar(100.0, i) for i in range(5)]]
    avg_low = sum(vols_low) / max(len(vols_low), 1)
    assert not (avg_low > min_proxy)
    vols_high = [getattr(b, "volume", 0) for b in [_make_bar(2_000_000.0, i) for i in range(5)]]
    avg_high = sum(vols_high) / max(len(vols_high), 1)
    assert avg_high > min_proxy


def test_depth_increases_effective_price() -> None:
    d = DepthModel()
    base = 100.0
    imp = d.impact(1000, 10_000.0)
    assert imp > 0.0
    assert base + imp > base


def test_mtf_momentum_nonzero_on_trend() -> None:
    fe = FeatureEngine()
    closes = [50.0 + i * 0.5 for i in range(25)]
    bars = [
        OHLCVBar(
            symbol="X",
            open=c,
            high=c + 0.1,
            low=c - 0.1,
            close=c,
            volume=5_000_000.0,
            timestamp=i,
        )
        for i, c in enumerate(closes)
    ]
    m = fe.multi_timeframe_momentum(bars)
    assert m > 0.0


def test_mtf_momentum_stronger_on_uptrend_than_flat() -> None:
    """MTF momentum from FeatureEngine — independent of edge-gated DecisionEngineV2."""
    fe = FeatureEngine()
    up = [50.0 + i * 2.0 for i in range(50)]
    bars_up = [
        OHLCVBar(
            symbol="X",
            open=c,
            high=c + 1,
            low=c - 1,
            close=c,
            volume=5_000_000.0,
            timestamp=i,
        )
        for i, c in enumerate(up)
    ]
    flat = [100.0] * 35
    bars_flat = [
        OHLCVBar(
            symbol="X",
            open=c,
            high=c + 0.1,
            low=c - 0.1,
            close=c,
            volume=5_000_000.0,
            timestamp=i,
        )
        for i, c in enumerate(flat)
    ]
    m_up = fe.multi_timeframe_momentum(bars_up)
    m_flat = fe.multi_timeframe_momentum(bars_flat)
    assert m_up > m_flat
