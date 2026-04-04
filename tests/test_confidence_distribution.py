"""PRDV3: confidence must not collapse — spread across symbols/states (deterministic)."""

from __future__ import annotations

import pytest

from bist_core.decision.institutional_brain import compute_institutional_decision
from bist_core.models.ohlcv import OHLCVBar


def _bars_ramp(symbol: str, start: float, slope: float, n: int = 55) -> list[OHLCVBar]:
    out: list[OHLCVBar] = []
    for i in range(n):
        c = start + float(i) * slope
        out.append(
            OHLCVBar(
                timestamp=i,
                symbol=symbol,
                open=c,
                high=c + 0.6,
                low=max(c - 0.6, 0.01),
                close=c,
                volume=5000.0 + float(i) * 3.0,
            )
        )
    return out


def test_confidence_spread_across_paths_min_range() -> None:
    """max(conf) - min(conf) > 0.25 on distinct deterministic paths."""
    confs: list[float] = []
    for sym, st, sl in (
        ("ASELS", 42.0, 0.12),
        ("SISE", 8.0, -0.09),
        ("GARAN", 3.2, 0.04),
        ("THYAO", 180.0, -0.02),
        ("AKBNK", 5.5, 0.11),
    ):
        bars = _bars_ramp(sym, st, sl)
        d = compute_institutional_decision(
            bars,
            float(bars[-1].close),
            symbol=sym,
            recent_signatures=[],
            bar_ts=int(bars[-1].timestamp),
        )
        if str(d.get("state")) == "INSUFFICIENT_DATA":
            continue
        confs.append(float(d.get("confidence") or 0.0))
    assert len(confs) >= 3
    spread = max(confs) - min(confs)
    assert spread > 0.25, f"confidence collapsed: spread={spread} confs={confs}"


def test_confidence_bounded_0_2_to_0_9() -> None:
    bars = _bars_ramp("X", 10.0, 0.1)
    d = compute_institutional_decision(
        bars,
        float(bars[-1].close),
        symbol="X",
        recent_signatures=[],
        bar_ts=1,
    )
    c = float(d.get("confidence") or 0.0)
    assert 0.2 - 1e-6 <= c <= 0.9 + 1e-6
