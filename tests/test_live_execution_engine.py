"""Live execution engine — deterministic fills + slippage.

Note: basename must differ from ``tests/module/test_execution_engine_module.py`` (order book) for pytest.
"""

from __future__ import annotations

from bist_core.live.execution_engine import ExecutionEngine


def test_fill_logic_runs() -> None:
    eng = ExecutionEngine()
    r = eng.try_fill("X", "enter", 100.0, 100.0, 0.5)
    assert "filled" in r


def test_slippage_positive() -> None:
    eng = ExecutionEngine()
    r = eng.try_fill("X", "enter", 100.0, 100.0, 1.0)
    if r["filled"]:
        assert r["fill_price"] >= 100.0


def test_try_fill_deterministic() -> None:
    e1 = ExecutionEngine()
    e2 = ExecutionEngine()
    a = e1.try_fill("Z", "exit", 50.0, 50.0, 0.8)
    b = e2.try_fill("Z", "exit", 50.0, 50.0, 0.8)
    assert a == b
