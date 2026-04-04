from __future__ import annotations

from bist_core.services.symbol_comparison import compare_symbol_results


def test_compare_symbol_results_exposes_dual_rationale_contract() -> None:
    got = compare_symbol_results(
        [
            {
                "symbol": "AAA",
                "score": 1.2,
                "decision": "buy",
                "ret1_pct": 1.1,
                "range_pos": 0.7,
                "vol_ratio": 1.2,
                "current_close": 110.0,
                "ma20": 105.0,
            },
            {
                "symbol": "BBB",
                "score": 0.9,
                "decision": "watch",
                "ret1_pct": 0.2,
                "range_pos": 0.4,
                "vol_ratio": 0.8,
                "current_close": 99.0,
                "ma20": 101.0,
            },
        ]
    )

    decision_object = got.get("decision_object") or {}
    rationale = decision_object.get("rationale") or {}
    assert "A" in rationale
    assert "B" in rationale
    diff_table = decision_object.get("diff_table")
    assert isinstance(diff_table, list)
    assert len(diff_table) >= 3

