from bist_core.brain.scoring_engine import score_symbol, rank_symbols, SCORE_THRESHOLD


def _feats(momentum_20, ema_20, sma_50, rsi_14, atr_14):
    return {
        "momentum_20": [momentum_20],
        "ema_20": [ema_20],
        "sma_50": [sma_50],
        "rsi_14": [rsi_14],
        "atr_14": [atr_14],
    }


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
