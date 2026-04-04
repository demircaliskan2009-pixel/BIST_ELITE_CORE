"""PRDV3: institutional brain discriminates symbols, regimes, and edge scores (deterministic)."""

from __future__ import annotations

from bist_core.decision.institutional_brain import compute_institutional_decision
from bist_core.models.ohlcv import OHLCVBar


def _bars(symbol: str, closes: list[float]) -> list[OHLCVBar]:
    """Minimal OHLCV from close path (≥50 bars required)."""
    out: list[OHLCVBar] = []
    for i, c in enumerate(closes):
        cf = float(c)
        out.append(
            OHLCVBar(
                symbol=symbol,
                open=cf,
                high=cf + 0.02,
                low=max(cf - 0.02, 0.01),
                close=cf,
                volume=1000.0 + float(i),
                timestamp=i,
            )
        )
    return out


def _decide(bars: list[OHLCVBar], *, symbol: str, bar_ts: int = 1):
    last = float(bars[-1].close)
    return compute_institutional_decision(
        bars,
        last,
        symbol=symbol,
        recent_signatures=[],
        bar_ts=bar_ts,
    )


def test_brain_outputs_differ_for_symbols() -> None:
    # Distinct price paths → distinct features (symbol labels differ; paths must differ for discrimination).
    c_asels = [100.0 + i * 0.12 for i in range(80)]
    c_garan = [10.0 + (i % 3) * 0.01 for i in range(80)]

    b1 = _bars("ASELS", c_asels)
    b2 = _bars("GARAN", c_garan)

    out1 = _decide(b1, symbol="ASELS")
    out2 = _decide(b2, symbol="GARAN")

    assert out1 != out2


def test_brain_regime_changes_output() -> None:
    trending = _bars("X", [float(100 + i) for i in range(100)])
    ranging = _bars("X", [100.0 + float(i % 2) for i in range(200)])

    out1 = _decide(trending, symbol="X")
    out2 = _decide(ranging, symbol="X")

    assert out1 != out2


def test_edge_score_not_constant() -> None:
    ctxs = [
        _bars("A", [float(100 + i) for i in range(100)]),
        _bars("B", [100.0] * 100),
        _bars("C", [100.0 + float(i % 2) * 0.5 for i in range(100)]),
    ]

    scores = [_decide(b, symbol=s)["edge_score"] for b, s in zip(ctxs, ("A", "B", "C"), strict=True)]

    assert len(set(scores)) > 1
