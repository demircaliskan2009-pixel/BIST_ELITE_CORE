from bist_core.backtest.backtest_engine import OHLCVBar
from bist_core.brain.regime_engine import RegimeEngine
from bist_core.brain.scoring_engine import (
    SCORE_THRESHOLD,
    rank_symbols,
    score_edge,
    score_edges,
    score_symbol,
)
from bist_core.edge.registry import build_builtin_edge_registry


def _feats(momentum_20, ema_20, sma_50, rsi_14, atr_14):
    return {
        "momentum_20": [momentum_20],
        "ema_20": [ema_20],
        "sma_50": [sma_50],
        "rsi_14": [rsi_14],
        "atr_14": [atr_14],
    }


def _bar(ts: int, close: float, spread: float, volume: float) -> OHLCVBar:
    open_price = close - (spread * 0.2)
    high = close + spread
    low = max(close - spread, 0.01)
    return OHLCVBar(ts, "X", open_price, high, low, close, volume)


def _trend_up_bars(n: int = 60) -> list[OHLCVBar]:
    return [_bar(1_704_067_200 + i * 86400, 100.0 + i * 0.45, 0.55, 1_000_000.0) for i in range(n)]


def _range_bars(n: int = 60) -> list[OHLCVBar]:
    closes = [100.0 + ((i % 4) - 1.5) * 0.18 for i in range(n)]
    return [_bar(1_704_067_200 + i * 86400, close, 0.28, 900_000.0) for i, close in enumerate(closes)]


def test_momentum_none_returns_none():
    feats = _feats(momentum_20=0.03, ema_20=10.0, sma_50=10.0, rsi_14=50.0, atr_14=0.5)
    feats["momentum_20"] = [None]
    assert score_symbol("X", feats, 10.0) is None


def test_conflict_momentum_up_trend_down_applies_penalty():
    """Conflict (m>0, t<0) applies 0.30 penalty instead of returning None."""
    feats = _feats(momentum_20=0.03, ema_20=48.0, sma_50=55.0, rsi_14=45.0, atr_14=1.0)
    result = score_symbol("X", feats, 55.0)
    assert result is not None
    assert result["score"] < 0


def test_conflict_momentum_down_trend_up_applies_penalty():
    """Conflict (m<0, t>0) applies 0.30 penalty instead of returning None."""
    feats = _feats(momentum_20=-0.03, ema_20=58.0, sma_50=50.0, rsi_14=55.0, atr_14=1.0)
    result = score_symbol("X", feats, 50.0)
    assert result is not None
    assert result["score"] < 0


def test_aligned_bullish_scores_above_threshold():
    feats = _feats(momentum_20=0.03, ema_20=58.0, sma_50=50.0, rsi_14=40.0, atr_14=0.5)
    result = score_symbol("BULL", feats, 53.0)
    assert result is not None
    assert result["score"] >= SCORE_THRESHOLD
    assert result["symbol"] == "BULL"


def test_aligned_bearish_scores_below_zero():
    feats = _feats(momentum_20=-0.03, ema_20=42.0, sma_50=50.0, rsi_14=65.0, atr_14=1.0)
    result = score_symbol("BEAR", feats, 47.0)
    assert result is not None
    assert result["score"] < 0


def test_rank_filters_below_threshold():
    scored = [{"symbol": "A", "score": 0.10}, {"symbol": "B", "score": 0.30}]
    ranked = rank_symbols(scored, threshold=0.25)
    assert len(ranked) == 1
    assert ranked[0]["symbol"] == "B"


def test_rank_empty_returns_empty():
    assert rank_symbols([]) == []


def test_no_data_returns_none():
    assert score_symbol("X", {}, 50.0) is None


def test_score_edge_returns_positive_score_for_compatible_builtin_trend_edge() -> None:
    registry = build_builtin_edge_registry()
    edge = registry.list_active_edges()[0]
    bars = _trend_up_bars()
    regime = RegimeEngine().detect_regime(bars)

    result = score_edge(edge, regime, bars)

    assert result.edge_id == edge.edge_id
    assert result.total_score > 0
    assert result.components.regime_score > 0
    assert result.components.signal_score > 0
    assert "regime_score=" in result.explanation


def test_score_edge_fail_closes_on_regime_mismatch() -> None:
    registry = build_builtin_edge_registry()
    edge = registry.list_active_edges()[0]
    bars = _range_bars()
    regime = RegimeEngine().detect_regime(bars)

    result = score_edge(edge, regime, bars)

    assert result.total_score == 0.0
    assert "regime_mismatch" in result.explanation


def test_score_edge_fail_closes_on_unclear_signal() -> None:
    registry = build_builtin_edge_registry()
    edge = registry.list_active_edges()[0]
    bars = _trend_up_bars()
    regime = RegimeEngine().detect_regime(bars)
    last = bars[-1]
    bars[-1] = OHLCVBar(
        last.timestamp,
        last.symbol,
        last.open,
        last.high,
        max(last.low - 10.0, 0.01),
        max(last.close - 12.0, 0.01),
        last.volume,
    )

    result = score_edge(edge, regime, bars)

    assert result.total_score == 0.0
    assert "unclear_signal" in result.explanation


def test_score_edge_fail_closes_on_insufficient_history() -> None:
    registry = build_builtin_edge_registry()
    edge = registry.list_active_edges()[0]
    bars = _trend_up_bars(30)
    regime = RegimeEngine().detect_regime(_trend_up_bars())

    result = score_edge(edge, regime, bars)

    assert result.total_score == 0.0
    assert "insufficient_history" in result.explanation


def test_score_edges_returns_all_active_edges_without_ranking() -> None:
    registry = build_builtin_edge_registry()
    bars = _trend_up_bars()
    regime = RegimeEngine().detect_regime(bars)

    results = score_edges(registry, regime, bars)

    assert len(results) == 2
    assert tuple(result.edge_id for result in results) == (
        "bist_bull_pullback_sma20",
        "bist_sideways_rsi_reversion",
    )
    assert results[0].total_score > 0
    assert results[1].total_score == 0.0
