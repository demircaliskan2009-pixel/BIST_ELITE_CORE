"""FAZ85: Corporate actions adjustment — split/bedelsiz (bonus_issue) deterministic via market module."""
from __future__ import annotations

from pathlib import Path

import pytest

from bist_core.market.corporate_actions_apply import apply_corporate_actions, load_actions_from_csv

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "market"


def test_faz85_split_and_bedelsiz_deterministic(tmp_path: Path) -> None:
    """Load fixture CA (split + bonus_issue), apply to bars; adjusted closes deterministic."""
    ca_path = FIXTURES / "corporate_actions.csv"
    if not ca_path.is_file():
        (tmp_path / "corporate_actions.csv").write_text(
            "symbol,effective_date,kind,ratio\nX,2024-01-02,split,2\nY,2024-01-03,bonus_issue,1.5\n",
            encoding="utf-8",
        )
        ca_path = tmp_path / "corporate_actions.csv"
    actions = load_actions_from_csv(ca_path)
    assert len(actions) >= 2
    kinds = {a["kind"] for a in actions}
    assert "split" in kinds
    assert "bonus_issue" in kinds

    bars = [
        {"symbol": "X", "date": "2024-01-01", "close": 100.0},
        {"symbol": "X", "date": "2024-01-02", "close": 60.0},
        {"symbol": "Y", "date": "2024-01-01", "close": 15.0},
        {"symbol": "Y", "date": "2024-01-03", "close": 15.0},
    ]
    adjusted1, notes1 = apply_corporate_actions(bars, actions)
    adjusted2, notes2 = apply_corporate_actions(bars, actions)
    assert len(adjusted1) == len(bars)
    for a, b in zip(adjusted1, adjusted2):
        assert a["symbol"] == b["symbol"]
        assert a["date"] == b["date"]
        assert a["close"] == b["close"]

    by_key = {(r["symbol"], r["date"]): r["close"] for r in adjusted1}
    assert by_key[("X", "2024-01-01")] == 50.0
    assert by_key[("X", "2024-01-02")] == 60.0
    assert by_key[("Y", "2024-01-01")] == 10.0
    assert by_key[("Y", "2024-01-03")] == 15.0


def test_faz85_load_actions_from_fixture_csv() -> None:
    """Load actions from fixtures/market/corporate_actions.csv; deterministic order."""
    ca_path = FIXTURES / "corporate_actions.csv"
    if not ca_path.is_file():
        pytest.skip("fixtures/market/corporate_actions.csv not found")
    actions = load_actions_from_csv(ca_path)
    assert len(actions) == 2
    assert actions[0]["symbol"] == "X"
    assert actions[0]["kind"] == "split"
    assert actions[0]["ratio"] == 2.0
    assert actions[1]["symbol"] == "Y"
    assert actions[1]["kind"] == "bonus_issue"
    assert actions[1]["ratio"] == 1.5
