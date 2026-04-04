from __future__ import annotations

from bist_core.services.single_symbol_brief import build_single_symbol_brief


def test_build_single_symbol_brief_renders_levels_and_live_text() -> None:
    got = build_single_symbol_brief(
        {
            "symbol": "ASELS",
            "decision": "buy",
            "score": 4.6,
            "entry": 71.0,
            "stop": 69.5,
            "target": 76.0,
            "rationale": "Momentum güçlü",
        },
        {
            "current_price": 72.6500015258789,
            "last_price": 72.65,
            "price": 72.65,
        },
    )
    assert "ASELS" in got
    assert "karar=buy" in got
    assert "score=4.60" in got
    assert "giriş=71.00" in got
    assert "stop=69.50" in got
    assert "hedef=76.00" in got
    assert "Momentum güçlü" in got
    assert "giriş kaçmış" in got
    assert "geri çekilme" in got


def test_build_single_symbol_brief_uses_embedded_live_payload() -> None:
    got = build_single_symbol_brief(
        {
            "symbol": "AKBNK",
            "decision": "buy",
            "entry_price": 71.0,
            "live_payload": {
                "current_price": 72.6500015258789,
                "last_price": 72.65,
                "price": 72.65,
            },
        }
    )
    assert "AKBNK" in got
    assert "giriş kaçmış" in got


def test_build_single_symbol_brief_handles_missing_symbol() -> None:
    assert build_single_symbol_brief({"decision": "buy"}) == ""
