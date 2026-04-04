"""PRDV3: execution realism — no guaranteed fills, deterministic draw."""

from __future__ import annotations

from bist_core.live.execution_engine import ExecutionEngine


def test_fill_not_always_true() -> None:
    eng = ExecutionEngine()

    results = []
    for i in range(20):
        r = eng.try_fill("X", "enter", 100.0, 100.0 + i, 0.1)
        results.append(r["filled"])

    assert not all(results), "ALL FILLS = FAKE MARKET"
