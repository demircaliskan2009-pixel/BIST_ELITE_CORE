"""Tests for ATR stop/target risk sizing (live execution layer)."""

from __future__ import annotations

import pytest

from bist_core.live.stop_target_risk import (
    atr14_sma,
    compute_atr_stop_target,
    vol_stop_scale,
)
from bist_core.models.ohlcv import OHLCVBar


def _bars_uptrend(n: int, start: float = 100.0, step: float = 0.5) -> list[OHLCVBar]:
    out: list[OHLCVBar] = []
    p = start
    for i in range(n):
        o = p
        c = p + step
        h = max(o, c) + 0.2
        l = min(o, c) - 0.2
        out.append(
            OHLCVBar(
                timestamp=1000 + i,
                symbol="TST",
                open=o,
                high=h,
                low=l,
                close=c,
                volume=1_000_000.0,
            )
        )
        p = c
    return out


def test_atr14_sma_requires_15_bars() -> None:
    assert atr14_sma(_bars_uptrend(14)) == 0.0
    a = atr14_sma(_bars_uptrend(20))
    assert a > 0


def test_vol_stop_scale_low_vol_widens() -> None:
    s_low = vol_stop_scale(0.005)
    s_high = vol_stop_scale(0.08)
    assert s_low > s_high


def test_compute_long_rr_at_least_1_5(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BIST_STOP_ATR_K", raising=False)
    monkeypatch.delenv("BIST_STOP_RR_MIN", raising=False)
    bars = _bars_uptrend(25, start=50.0, step=0.3)
    dbg = compute_atr_stop_target(
        55.0,
        is_short=False,
        bars=bars,
        vol_norm=0.02,
    )
    assert dbg is not None
    assert dbg["stop"] < dbg["entry"] < dbg["target"]
    assert dbg["rr"] + 1e-9 >= 1.5
    assert dbg["atr"] > 0


def test_compute_short_symmetric(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BIST_STOP_ATR_K", raising=False)
    bars = _bars_uptrend(25, start=50.0, step=0.3)
    dbg = compute_atr_stop_target(
        55.0,
        is_short=True,
        bars=bars,
        vol_norm=0.02,
    )
    assert dbg is not None
    assert dbg["target"] < dbg["entry"] < dbg["stop"]
    assert dbg["rr"] + 1e-9 >= 1.5


def test_k_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BIST_STOP_ATR_K", "3.0")
    monkeypatch.delenv("BIST_STOP_RR_MIN", raising=False)
    bars = _bars_uptrend(25)
    d1 = compute_atr_stop_target(
        float(bars[-1].close),
        is_short=False,
        bars=bars,
        vol_norm=0.02,
    )
    monkeypatch.setenv("BIST_STOP_ATR_K", "1.0")
    d2 = compute_atr_stop_target(
        float(bars[-1].close),
        is_short=False,
        bars=bars,
        vol_norm=0.02,
    )
    assert d1 is not None and d2 is not None
    risk1 = d1["entry"] - d1["stop"]
    risk2 = d2["entry"] - d2["stop"]
    assert risk1 > risk2
