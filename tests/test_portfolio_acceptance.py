"""PRDV3: portfolio ranking, size limits, edge filtering, positive sizing."""

from __future__ import annotations

from bist_core.brain.ranking_engine import rank_symbols
from bist_core.live.portfolio_engine import build_portfolio_payload
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


def _enter_pack(
    sym: str,
    *,
    confidence: float,
    edge_score: float,
    cap: float = 100_000.0,
) -> dict[str, object]:
    bars = _bars(sym, 0.02)
    price = float(bars[-1].close)
    return {
        "decision": {
            "action": "enter",
            "confidence": confidence,
            "position_size": cap * 0.02,
            "entry": price,
            "stop_loss": price * 0.95,
            "target": price * 1.05,
            "brain_momentum": 0.08,
            "reason": "inst_enter|OK|test",
            "edge_score": edge_score,
            "edge": edge_score,
        },
        "bars": bars,
        "capital": cap,
        "current_price": price,
    }


def test_high_edge_selected_first() -> None:
    decisions = [
        {"symbol": "A", "edge_score": 0.2},
        {"symbol": "B", "edge_score": 0.8},
        {"symbol": "C", "edge_score": 0.5},
    ]

    ranked = rank_symbols(decisions)

    assert ranked[0]["symbol"] == "B"


def test_portfolio_max_size() -> None:
    cap = 100_000.0
    per: dict[str, dict[str, object]] = {}
    for i in range(20):
        sym = f"S{i}"
        per[sym] = _enter_pack(sym, confidence=0.56, edge_score=0.60 + i * 0.001, cap=cap)

    out = build_portfolio_payload(per, symbols_scanned=list(per.keys()))

    assert len(out["PORTFOLIO"]) <= 5
    assert out["SELECTED"] <= 5


def test_low_edge_filtered() -> None:
    """Low ``edge_score`` is dropped by ``rank_symbols``; include two high-edge names so
    the portfolio reaches ≥2 rows without the force-pool path (which ignores edge).
    """
    cap = 100_000.0
    per = {
        "A": _enter_pack("A", confidence=0.56, edge_score=0.01, cap=cap),
        "B": _enter_pack("B", confidence=0.56, edge_score=0.9, cap=cap),
        "C": _enter_pack("C", confidence=0.56, edge_score=0.88, cap=cap),
    }

    out = build_portfolio_payload(per, symbols_scanned=list(per.keys()))

    symbols = [str(x["symbol"]) for x in out["PORTFOLIO"]]

    assert "A" not in symbols
    assert "B" in symbols
    assert "C" in symbols


def test_position_size_valid() -> None:
    cap = 100_000.0
    per = {"A": _enter_pack("A", confidence=0.56, edge_score=0.9, cap=cap)}

    out = build_portfolio_payload(per, symbols_scanned=["A"])

    assert out["SELECTED"] >= 1
    assert len(out["PORTFOLIO"]) >= 1
    pos = float(out["PORTFOLIO"][0]["position_size"])
    assert pos > 0
