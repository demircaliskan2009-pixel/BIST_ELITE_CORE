from bist_core.brain.decision_engine import evaluate, rank_decisions, _entry_status, _build_rationale


def _score_result(score: float, m: float = 0.5, t: float = 0.5):
    return {
        "score": score,
        "features": {"momentum": m, "trend": t, "rsi_signal": 0.1, "vol_penalty": 0.2},
        "reason": "test",
    }


def test_entry_status_valid():
    assert _entry_status(100.0, 100.0, 98.0) == "valid"


def test_entry_status_missed():
    assert _entry_status(106.0, 100.0, 98.0) == "missed"


def test_entry_status_pullback():
    assert _entry_status(98.5, 100.0, 97.0) == "pullback"


def test_entry_status_below_stop():
    assert _entry_status(96.0, 100.0, 98.0) == "below_stop"


def test_evaluate_skip_on_low_score():
    r = evaluate("X", _score_result(0.10), 100.0, 98.0, 104.0)
    assert r["action"] == "skip"


def test_evaluate_skip_on_low_rr():
    r = evaluate("X", _score_result(0.50), 100.0, 99.5, 100.5)
    assert r["action"] == "skip"
    assert "rr_ratio_too_low" in r["reason"]


def test_evaluate_enter_on_valid():
    r = evaluate("X", _score_result(0.60), 100.0, 96.0, 110.0)
    assert r["action"] == "enter"
    assert r["confidence"] > 0
    assert r["entry_status"] == "valid"


def test_evaluate_no_score_skips():
    r = evaluate("X", None, 100.0, 98.0, 104.0)
    assert r["action"] == "skip"


def test_rationale_is_data_driven():
    r1 = _build_rationale({"momentum": 0.8, "trend": 0.5, "rsi_signal": 0.4, "vol_penalty": 0.1}, 0.6)
    r2 = _build_rationale({"momentum": -0.8, "trend": -0.5, "rsi_signal": -0.4, "vol_penalty": 0.8}, 0.1)
    assert r1 != r2
    assert "momentum" in r1 or "trend" in r1


def test_rank_decisions_enter_first():
    decisions = [
        {"symbol": "A", "action": "wait", "confidence": 0.9, "score": 0.9},
        {"symbol": "B", "action": "enter", "confidence": 0.6, "score": 0.6},
        {"symbol": "C", "action": "enter", "confidence": 0.8, "score": 0.8},
    ]
    ranked = rank_decisions(decisions)
    assert ranked[0]["symbol"] == "C"
    assert ranked[1]["symbol"] == "B"


def test_different_symbols_different_reasons():
    r1 = evaluate("SYM1", _score_result(0.6, m=0.9, t=0.8), 100.0, 95.0, 115.0)
    r2 = evaluate("SYM2", _score_result(0.3, m=0.1, t=0.1), 100.0, 95.0, 115.0)
    assert r1["reason"] != r2["reason"]
