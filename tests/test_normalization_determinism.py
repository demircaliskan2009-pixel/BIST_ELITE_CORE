"""PRDV3: ``normalize_price`` is pure and deterministic."""

from __future__ import annotations

from bist_core.live.data_feed import normalize_price


def test_normalization_is_deterministic() -> None:
    vals = [0.5, 1.2, 3.5, 10, 100, 350]

    out1 = [normalize_price(x) for x in vals]
    out2 = [normalize_price(x) for x in vals]

    assert out1 == out2


def test_normalization_stability() -> None:
    raw = [1.5, 2.0, 3.0, 100, 200, 300]

    normalized = [normalize_price(x) for x in raw]

    assert all(10 < x < 10000 for x in normalized)
