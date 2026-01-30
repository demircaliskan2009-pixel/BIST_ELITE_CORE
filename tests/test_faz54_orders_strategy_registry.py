"""FAZ54: Orders strategy registry (resolve_strategy, deterministic top_n + stable ordering)."""
from __future__ import annotations

import pytest

from bist_core.orders.strategies import resolve_strategy, list_strategies


def test_resolve_strategy_equal_weight() -> None:
    """resolve_strategy('equal_weight') returns strategy with build_intent."""
    strat = resolve_strategy("equal_weight")
    assert strat.name == "equal_weight"
    out = strat.build_intent(
        day="2099-04-01",
        universe=["A", "B"],
        advice_records=[
            {"symbol": "A", "score": 0.5, "decision_raw": "BUY"},
            {"symbol": "B", "score": 0.3, "decision_raw": "BUY"},
        ],
        params={"top_n": 10},
    )
    assert out["schema_version"] == 1
    assert out["strategy"]["name"] == "equal_weight"
    assert len(out["actions"]) == 2
    assert [a["symbol"] for a in out["actions"]] == ["A", "B"]
    assert all(a["weight"] == 0.5 for a in out["actions"])


def test_resolve_strategy_unknown_raises() -> None:
    """resolve_strategy('unknown') raises ValueError."""
    with pytest.raises(ValueError, match="UnknownStrategy:unknown"):
        resolve_strategy("unknown")


def test_list_strategies_sorted() -> None:
    """list_strategies returns sorted strategy names."""
    names = list_strategies()
    assert isinstance(names, list)
    assert names == sorted(names)
    assert "equal_weight" in names
    assert "deny_all" in names


def test_equal_weight_deterministic_top_n_and_ordering() -> None:
    """Same advice_records + top_n => identical actions (deterministic, stable order)."""
    strat = resolve_strategy("equal_weight")
    advice = [
        {"symbol": "X", "score": 0.9, "decision_raw": "BUY"},
        {"symbol": "Y", "score": 0.8, "decision_raw": "BUY"},
        {"symbol": "Z", "score": 0.7, "decision_raw": "BUY"},
    ]
    params = {"top_n": 2}
    out1 = strat.build_intent(day="2099-04-02", universe=["X", "Y", "Z"], advice_records=advice, params=params)
    out2 = strat.build_intent(day="2099-04-02", universe=["X", "Y", "Z"], advice_records=advice, params=params)
    assert out1["actions"] == out2["actions"]
    assert len(out1["actions"]) == 2
    symbols = [a["symbol"] for a in out1["actions"]]
    assert symbols == sorted(symbols)
    assert out1["actions"][0]["weight"] == 0.5 and out1["actions"][1]["weight"] == 0.5


def test_deny_all_via_registry() -> None:
    """resolve_strategy('deny_all') returns strategy that produces no actions."""
    strat = resolve_strategy("deny_all")
    assert strat.name == "deny_all"
    out = strat.build_intent(
        day="2099-04-03",
        universe=["A", "B"],
        advice_records=[{"symbol": "A", "decision_raw": "BUY"}],
        params={},
    )
    assert out["actions"] == []
    assert "no_actions" in out["notes"]
