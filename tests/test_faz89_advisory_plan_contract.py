"""FAZ89: Advisory plan contract — same inputs -> same output hash (deterministic)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from bist_core.advisory.plan import build_advisory_plan, write_advisory_plan


def test_faz89_same_input_same_output_hash(tmp_path: Path) -> None:
    """Same signals + rules + portfolio snapshot -> same advisory_plan.json content hash."""
    signals = [
        {"symbol": "X", "score": 1.0, "side": "BUY"},
        {"symbol": "Y", "score": -0.5, "side": "SELL"},
    ]
    rules = {"max_positions": 10, "max_names": 5}
    portfolio_snapshot = {"cash": 1000.0, "positions": {"X": {"qty": 10, "cost_basis": 5.0}}}

    plan1 = build_advisory_plan(signals, rules, portfolio_snapshot)
    plan2 = build_advisory_plan(signals, rules, portfolio_snapshot)
    assert plan1 == plan2

    out1 = tmp_path / "out1" / "advisory_plan.json"
    out2 = tmp_path / "out2" / "advisory_plan.json"
    write_advisory_plan(out1, plan1)
    write_advisory_plan(out2, plan2)
    h1 = hashlib.sha256(out1.read_bytes()).hexdigest()
    h2 = hashlib.sha256(out2.read_bytes()).hexdigest()
    assert h1 == h2


def test_faz89_advisory_plan_deterministic_structure() -> None:
    """build_advisory_plan produces schema_version, planned_actions (sorted), rules_summary, portfolio_summary."""
    signals = [{"symbol": "A", "score": 0.1, "side": "BUY"}]
    rules = {"max_positions": 10}
    portfolio_snapshot = {"cash": 0.0, "positions": {}}
    plan = build_advisory_plan(signals, rules, portfolio_snapshot)
    assert plan["schema_version"] == 1
    assert "planned_actions" in plan
    assert plan["planned_actions"][0]["symbol"] == "A"
    assert "rules_summary" in plan
    assert "portfolio_summary" in plan
    assert plan["portfolio_summary"]["position_count"] == 0
    assert plan["portfolio_summary"]["symbols"] == []
