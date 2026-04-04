from __future__ import annotations

from bist_core.services.adjustments import apply_close_adjustments


def test_apply_close_adjustments_split() -> None:
    bars = [
        {"symbol": "AAA", "date": "2099-01-01", "close": 100.0},
        {"symbol": "AAA", "date": "2099-01-02", "close": 120.0},
    ]
    actions = [
        {
            "symbol": "AAA",
            "effective_date": "2099-01-02",
            "kind": "split",
            "ratio": 2.0,
        }
    ]
    adjusted, _ = apply_close_adjustments(bars, actions)
    assert adjusted[0]["close"] == 50.0
    assert adjusted[1]["close"] == 120.0
