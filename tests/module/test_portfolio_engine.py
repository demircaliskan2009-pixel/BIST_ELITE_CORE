"""Portfolio scan / ranking — deterministic, no network."""

from __future__ import annotations

import pytest

from bist_core.live.portfolio_engine import (
    DEFAULT_BIST_SYMBOLS,
    build_portfolio_payload,
    load_symbol_universe_from_env,
    normalize_scores_to_unit_interval,
    raw_ranking_score,
)
from bist_core.models.ohlcv import OHLCVBar


def _bars(sym: str, slope: float, n: int = 55) -> list[OHLCVBar]:
    out: list[OHLCVBar] = []
    for i in range(n):
        c = 100.0 + float(i) * slope
        out.append(
            OHLCVBar(
                timestamp=i,
                symbol=sym,
                open=c,
                high=c + 0.1,
                low=c - 0.1,
                close=c,
                volume=1000.0 + float(i),
            )
        )
    return out


def test_default_universe_len() -> None:
    assert len(DEFAULT_BIST_SYMBOLS) == 10


def test_load_symbol_universe_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BIST_SYMBOLS", " X, Y ")
    assert load_symbol_universe_from_env() == ["X", "Y"]
    monkeypatch.delenv("BIST_SYMBOLS", raising=False)
    monkeypatch.setenv("BIST_LIVE_SYMBOLS", "A,B")
    assert load_symbol_universe_from_env() == ["A", "B"]


def test_normalize_scores() -> None:
    assert normalize_scores_to_unit_interval([0.0, 2.0, 4.0]) == [0.0, 0.5, 1.0]
    assert normalize_scores_to_unit_interval([]) == []


def test_thr_get_override(monkeypatch: pytest.MonkeyPatch) -> None:
    import bist_core.live.portfolio_engine as pe

    monkeypatch.setenv("BIST_PORTFOLIO_MIN_CONF", "0.99")
    assert (
        pe._thr_get("min_conf", "BIST_PORTFOLIO_MIN_CONF", "0.1", {"min_conf": 0.11})
        == 0.11
    )
    assert pe._thr_get("min_conf", "BIST_PORTFOLIO_MIN_CONF", "0.1", None) == 0.99


def test_raw_ranking_score_positive() -> None:
    r = raw_ranking_score(
        confidence=0.5,
        position_frac=0.02,
        momentum=0.1,
        vol=0.02,
        price=100.0,
    )
    assert r > 0


def test_build_portfolio_payload_selects_multiple() -> None:
    cap = 100_000.0
    per: dict[str, dict[str, object]] = {}
    for i, sym in enumerate(["ASELS", "THYAO", "GARAN", "AKBNK", "SISE"]):
        bars = _bars(sym, 0.02 + i * 0.001)
        per[sym] = {
            "decision": {
                "action": "enter",
                "confidence": 0.55 + i * 0.01,
                "edge_score": 0.60 + i * 0.02,
                "edge": 0.60 + i * 0.02,
                "position_size": cap * (0.005 + i * 0.001),
                "entry": float(bars[-1].close),
                "stop_loss": float(bars[-1].close) * 0.95,
                "target": float(bars[-1].close) * 1.05,
                "brain_momentum": 0.05 + i * 0.01,
                "reason": f"inst_enter|OK|r{i}",
            },
            "bars": bars,
            "capital": cap,
            "current_price": float(bars[-1].close),
        }
    scanned = list(per.keys())
    out = build_portfolio_payload(per, symbols_scanned=scanned)
    assert out["TOTAL_SYMBOLS_SCANNED"] == 5
    assert out["SELECTED"] >= 2
    assert len(out["PORTFOLIO"]) == out["SELECTED"]
    sizes = [float(p["position_size"]) for p in out["PORTFOLIO"]]
    scores = [float(p["score"]) for p in out["PORTFOLIO"]]
    assert len(set(round(s, 5) for s in scores)) >= 2
    assert len(set(round(s, 5) for s in sizes)) >= 1


def test_build_portfolio_payload_single_hold_produces_portfolio() -> None:
    """Single valid hold must be selected (no collapse to empty when candidate exists)."""
    cap = 100_000.0
    bars = _bars("ASELS", 0.01)
    per = {
        "ASELS": {
            "decision": {
                "action": "hold",
                "confidence": 0.5,
                "edge_score": 0.25,
                "edge": 0.25,
                "reason": "x",
            },
            "bars": bars,
            "capital": cap,
            "current_price": float(bars[-1].close),
        }
    }
    out = build_portfolio_payload(per, symbols_scanned=["ASELS"])
    assert out["SELECTED"] >= 1
    assert len(out["PORTFOLIO"]) >= 1
    assert out["PORTFOLIO"][0]["symbol"] == "ASELS"


def test_two_holds_produces_portfolio() -> None:
    cap = 100_000.0
    per: dict[str, dict[str, object]] = {}
    for sym, slope in (("ASELS", 0.01), ("THYAO", -0.02)):
        bars = _bars(sym, slope)
        per[sym] = {
            "decision": {
                "action": "hold",
                "confidence": 0.4,
                "edge_score": 0.5 if sym == "ASELS" else 0.48,
                "edge": 0.5 if sym == "ASELS" else 0.48,
                "reason": "inst_hold|x|y",
            },
            "bars": bars,
            "capital": cap,
            "current_price": float(bars[-1].close),
        }
    out = build_portfolio_payload(per, symbols_scanned=list(per.keys()))
    assert out["SELECTED"] >= 2
    assert len(out["PORTFOLIO"]) >= 2


def test_mixed_hold_exit_partial_exit_selects_hold() -> None:
    """Cycle-25 scenario: 1 hold + 2 exit/partial_exit → portfolio must not be empty."""
    cap = 100_000.0
    per: dict[str, dict[str, object]] = {}
    for sym, action, slope in (
        ("ASELS", "partial_exit", 0.01),
        ("SISE", "hold", 0.02),
        ("GARAN", "exit", -0.01),
    ):
        bars = _bars(sym, slope)
        per[sym] = {
            "decision": {
                "action": action,
                "confidence": 0.5,
                "edge_score": 0.25,
                "edge": 0.25,
                "reason": f"inst_{action}|x",
            },
            "bars": bars,
            "capital": cap,
            "current_price": float(bars[-1].close),
        }
    out = build_portfolio_payload(per, symbols_scanned=list(per.keys()))
    assert out["SELECTED"] >= 1
    assert len(out["PORTFOLIO"]) >= 1
    symbols = [p["symbol"] for p in out["PORTFOLIO"]]
    assert "SISE" in symbols


def test_all_exit_remains_empty() -> None:
    """Genuine no-edge: all exit, no enters, no holds → fail-closed empty."""
    cap = 100_000.0
    per: dict[str, dict[str, object]] = {}
    for sym, slope in (("ASELS", 0.01), ("GARAN", -0.02)):
        bars = _bars(sym, slope)
        per[sym] = {
            "decision": {
                "action": "exit",
                "confidence": 0.5,
                "reason": "inst_exit|x",
            },
            "bars": bars,
            "capital": cap,
            "current_price": float(bars[-1].close),
        }
    out = build_portfolio_payload(per, symbols_scanned=list(per.keys()))
    assert out["SELECTED"] == 0
    assert out["PORTFOLIO"] == []


def test_build_portfolio_payload_orders_by_edge_score() -> None:
    """When edge_score is present, portfolio row order follows rank_symbols (best edge first)."""
    cap = 100_000.0
    per: dict[str, dict[str, object]] = {}
    for sym in ("LOW", "HIGH"):
        bars = _bars(sym, 0.02)
        per[sym] = {
            "decision": {
                "action": "enter",
                "confidence": 0.55,
                "position_size": cap * 0.01,
                "entry": float(bars[-1].close),
                "stop_loss": float(bars[-1].close) * 0.95,
                "target": float(bars[-1].close) * 1.05,
                "brain_momentum": 0.05,
                "reason": "e",
                "edge_score": 0.65 if sym == "LOW" else 0.9,
                "edge": 0.65 if sym == "LOW" else 0.9,
            },
            "bars": bars,
            "capital": cap,
            "current_price": float(bars[-1].close),
        }
    out = build_portfolio_payload(per, symbols_scanned=list(per.keys()))
    assert out["SELECTED"] >= 2
    assert out["PORTFOLIO"][0]["symbol"] == "HIGH"


def test_confidence_spread_tight_band() -> None:
    cap = 100_000.0
    per: dict[str, dict[str, object]] = {}
    for i, sym in enumerate(["A", "B"]):
        bars = _bars(sym, 0.02 + i * 0.001)
        per[sym] = {
            "decision": {
                "action": "enter",
                "confidence": 0.55 + i * 0.02,
                "edge_score": 0.65,
                "edge": 0.65,
                "position_size": cap * 0.01,
                "entry": float(bars[-1].close),
                "stop_loss": float(bars[-1].close) * 0.95,
                "target": float(bars[-1].close) * 1.05,
                "brain_momentum": 0.1,
                "reason": f"e{i}",
            },
            "bars": bars,
            "capital": cap,
            "current_price": float(bars[-1].close),
        }
    out = build_portfolio_payload(per, symbols_scanned=["A", "B"])
    confs = [float(p["confidence"]) for p in out["PORTFOLIO"]]
    assert len(confs) >= 2
    assert max(confs) - min(confs) >= 0.01 - 1e-6
