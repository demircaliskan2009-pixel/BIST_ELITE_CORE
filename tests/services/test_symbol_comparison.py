from __future__ import annotations

from bist_core.services.symbol_comparison import (
    compare_symbol_results,
    normalize_symbol_result,
    render_comparison_text,
)


def test_normalize_symbol_result_extracts_core_fields() -> None:
    got = normalize_symbol_result(
        {
            "symbol": "akbnk",
            "score": 4.25,
            "decision": "buy",
            "entry_missed": False,
            "live_gap_pct": 0.52,
            "live_entry_text": "yakın",
        }
    )
    assert got["symbol"] == "AKBNK"
    assert got["score"] == 4.25
    assert got["decision_weight"] == 4
    assert got["entry_missed"] is False
    assert got["live_gap_pct"] == 0.52
    assert got["reason"] == "yakın"


def test_compare_symbol_results_ranks_by_score() -> None:
    got = compare_symbol_results(
        [
            {"symbol": "AKBNK", "score": 3.2, "decision": "buy"},
            {"symbol": "GARAN", "score": 4.1, "decision": "buy"},
            {"symbol": "ASELS", "score": 2.9, "decision": "watch"},
        ]
    )
    assert got["leader"]["symbol"] == "GARAN"
    assert got["symbols"] == ["GARAN", "AKBNK", "ASELS"]


def test_compare_symbol_results_breaks_tie_with_entry_missed() -> None:
    got = compare_symbol_results(
        [
            {"symbol": "AKBNK", "score": 4.0, "decision": "buy", "entry_missed": True},
            {"symbol": "GARAN", "score": 4.0, "decision": "buy", "entry_missed": False},
        ]
    )
    assert got["leader"]["symbol"] == "GARAN"
    assert got["leader"]["entry_missed"] is False


def test_compare_symbol_results_prefers_discount_when_scores_tied() -> None:
    got = compare_symbol_results(
        [
            {"symbol": "AKBNK", "score": 4.0, "decision": "buy", "entry_missed": False, "is_discount_to_entry": False},
            {"symbol": "GARAN", "score": 4.0, "decision": "buy", "entry_missed": False, "is_discount_to_entry": True},
        ]
    )
    assert got["leader"]["symbol"] == "GARAN"
    assert got["leader"]["is_discount_to_entry"] is True


def test_render_comparison_text_includes_ranking_and_reason() -> None:
    text = render_comparison_text(
        [
            {
                "symbol": "AKBNK",
                "score": 4.4,
                "decision": "buy",
                "entry_missed": False,
                "live_entry_text": "girişe yakın",
            },
            {
                "symbol": "GARAN",
                "score": 3.7,
                "decision": "watch",
                "entry_missed": True,
            },
        ]
    )
    assert "AKBNK önde" in text
    assert "1) AKBNK" in text
    assert "2) GARAN" in text
    assert "Lider notu: girişe yakın" in text


def test_render_comparison_text_handles_empty_input() -> None:
    assert render_comparison_text([]) == "Karşılaştırılacak geçerli sembol sonucu yok."
