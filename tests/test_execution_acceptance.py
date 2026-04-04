"""PRDV3: execution realism — fill/miss mix, slippage, determinism."""

from __future__ import annotations

from bist_core.live.execution_engine import ExecutionEngine


def test_fill_and_miss_exist():
    e = ExecutionEngine()
    results = []
    for i in range(20):
        r = e.try_fill(
            symbol="X",
            action="enter",
            price=100 + i,
            last_price=100,
            confidence=0.2,
        )
        results.append(r["filled"])
    assert any(results)
    assert not all(results)


def test_slippage_positive():
    e = ExecutionEngine()
    r = e.try_fill(
        symbol="X",
        action="enter",
        price=100,
        last_price=100,
        confidence=1.0,
    )
    if r["filled"]:
        assert r["fill_price"] != 100


def test_execution_deterministic():
    e = ExecutionEngine()
    r1 = e.try_fill("X", "enter", 100, last_price=100, confidence=0.5)
    r2 = e.try_fill("X", "enter", 100, last_price=100, confidence=0.5)
    assert r1 == r2
