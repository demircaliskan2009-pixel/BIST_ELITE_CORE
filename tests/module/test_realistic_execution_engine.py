"""RealisticExecutionEngine — deterministic spreads, fills, costs (no RNG)."""

from __future__ import annotations

import pytest

from bist_core.execution.realistic_execution_engine import RealisticExecutionEngine


def test_create_order_deterministic_ids() -> None:
    eng = RealisticExecutionEngine()
    a = eng.create_order("GARAN", "buy", 100.0, 1)
    b = eng.create_order("GARAN", "sell", 100.0, 1)
    assert a["id"] == "rfx:0000000001"
    assert b["id"] == "rfx:0000000002"


def test_spread_is_vol_times_point_zero_two() -> None:
    eng = RealisticExecutionEngine()
    o = eng.create_order("X", "buy", 100.0, 1)
    out = eng.process_fill(o, 0.05, volume_proxy=10_000.0)
    assert out is not None
    assert out["spread_fraction"] == pytest.approx(0.05 * 0.02)


def test_process_fill_returns_price() -> None:
    eng = RealisticExecutionEngine()
    o = eng.create_order("X", "buy", 100.0, 1)
    out = eng.process_fill(o, 0.02, volume_proxy=1000.0)
    assert out is not None
    assert out["filled_qty"] > 0
    assert out["price"] > 0
    assert "commission" in out and "spread_cost" in out
    assert out["slippage_fraction"] > 0
    assert out["mid_price"] == pytest.approx(100.0)


def test_liquidity_fail() -> None:
    eng = RealisticExecutionEngine()
    o = eng.create_order("X", "buy", 100.0, 1)
    # Below liquidity floor vs order notional — fail-closed (explicit bad depth).
    assert eng.process_fill(o, 0.02, volume_proxy=0.5) is None


def test_none_volume_proxy_is_not_automatic_full_fill() -> None:
    eng = RealisticExecutionEngine()
    o = eng.create_order("X", "buy", 100.0, 1)
    out = eng.process_fill(o, 0.05, volume_proxy=None)
    # Synthetic depth: either partial fill or deterministic miss (never guaranteed 100% fill).
    if out is None:
        return
    assert float(out["fill_ratio"]) < 1.0


def test_low_fill_ratio_fail_closed() -> None:
    eng = RealisticExecutionEngine()
    o = eng.create_order("X", "buy", 100.0, 1)
    assert eng.process_fill(o, 0.02, volume_proxy=40.0) is None


def test_deterministic_repeatable() -> None:
    eng = RealisticExecutionEngine()
    o1 = eng.create_order("ASELS", "buy", 50.0, 1)
    o2 = eng.create_order("ASELS", "buy", 50.0, 1)
    a = eng.process_fill(o1, 0.03, volume_proxy=500.0)
    b = eng.process_fill(o2, 0.03, volume_proxy=500.0)
    assert a is not None and b is not None
    assert a["price"] == b["price"]
    assert a["spread_fraction"] == b["spread_fraction"]


def test_size_fraction_increases_slippage() -> None:
    eng = RealisticExecutionEngine()
    o1 = eng.create_order("Z", "buy", 100.0, 1)
    o2 = eng.create_order("Z", "buy", 100.0, 1)
    low = eng.process_fill(
        o1, 0.05, volume_proxy=10_000.0, size_fraction=0.5
    )
    high = eng.process_fill(
        o2, 0.05, volume_proxy=10_000.0, size_fraction=1.0
    )
    assert low is not None and high is not None
    assert high["slippage_fraction"] >= low["slippage_fraction"]


def test_trend_worsens_buy_vs_sell_direction() -> None:
    eng = RealisticExecutionEngine()
    o = eng.create_order("T", "buy", 100.0, 1)
    flat = eng.process_fill(
        o, 0.04, volume_proxy=10_000.0, trend_abs=0.0
    )
    o2 = eng.create_order("T", "buy", 100.0, 1)
    up = eng.process_fill(o2, 0.04, volume_proxy=10_000.0, trend_abs=0.9)
    assert flat is not None and up is not None
    assert up["price"] >= flat["price"]
