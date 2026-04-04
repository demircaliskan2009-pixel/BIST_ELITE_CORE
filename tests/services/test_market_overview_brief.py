from __future__ import annotations

from bist_core.services.market_overview_brief import (
    build_market_overview_brief,
    build_market_overview_payload,
)


def test_build_market_overview_brief_summarizes_leader_and_top_symbols() -> None:
    got = build_market_overview_brief(
        [
            {"symbol": "AKBNK", "score": 4.4, "decision": "buy", "entry_missed": False, "live_entry_text": "girişe yakın"},
            {"symbol": "GARAN", "score": 3.7, "decision": "watch", "entry_missed": True},
            {"symbol": "ASELS", "score": 3.1, "decision": "hold", "entry_missed": False},
        ],
        top_n=3,
    )
    assert "AKBNK" in got
    assert "score=4.40" in got
    assert "Öne çıkanlar: AKBNK, GARAN, ASELS" in got
    assert "karar=buy" in got


def test_build_market_overview_brief_handles_empty_input() -> None:
    assert build_market_overview_brief([]) == ""


def test_build_market_overview_payload_returns_text_and_symbols() -> None:
    got = build_market_overview_payload(
        [
            {"symbol": "AKBNK", "score": 4.4, "decision": "buy", "entry_missed": False},
            {"symbol": "GARAN", "score": 3.7, "decision": "watch", "entry_missed": True},
        ],
        top_n=2,
    )
    assert got["leader"]["symbol"] == "AKBNK"
    assert got["symbols"] == ["AKBNK", "GARAN"]
    assert got["count"] == 2
    assert "AKBNK" in got["text"]
