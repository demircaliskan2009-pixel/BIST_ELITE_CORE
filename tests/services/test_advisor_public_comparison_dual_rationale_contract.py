from __future__ import annotations

from bist_core.services import advisor as advisor_mod

KNOWN = ["ASELS", "AKBNK", "GARAN", "THYAO", "TUPRS", "EREGL"]


def test_public_comparison_route_preserves_dual_rationale_and_factor_diff() -> None:
    original = advisor_mod.build_advice_for_symbol

    def fake_build_advice_for_symbol(symbol, date):
        payload = {
            "AKBNK": {
                "symbol": "AKBNK",
                "decision": "buy",
                "score": 3.9,
                "entry_missed": True,
                "compact_rationale": "Giriş uzamış, pullback gerekli.",
                "live_gap_pct": 3.4,
            },
            "GARAN": {
                "symbol": "GARAN",
                "decision": "buy",
                "score": 4.2,
                "is_discount_to_entry": True,
                "compact_rationale": "Relatif güç ve banka teması daha dengeli.",
                "live_gap_pct": 0.8,
            },
        }
        return payload[symbol]

    advisor_mod.build_advice_for_symbol = fake_build_advice_for_symbol
    try:
        got = advisor_mod.build_chat_response_for_text(
            "AKBNK ile GARAN karşılaştır",
            "2026-03-14",
            known_symbols=KNOWN,
            scan_universe=["AKBNK", "GARAN"],
        )
    finally:
        advisor_mod.build_advice_for_symbol = original

    assert got["ok"] is True
    assert got["route"] == "comparison"
    assert got["leader_symbol"] == "GARAN"
    assert got["resolved_symbols"] == ["AKBNK", "GARAN"]

    text = got["text"]
    assert "GARAN önde" in text
    assert "Neden GARAN önde:" in text
    assert "Neden AKBNK geride:" in text
    assert "Faktör farkları:" in text
    assert "skor | GARAN=4.20 | AKBNK=3.90 | fark=+0.30" in text
    assert "giriş durumu | GARAN=girişe göre indirimli | AKBNK=giriş kaçmış" in text
    assert "Lider notu: Relatif güç ve banka teması daha dengeli." in text
    assert "Rakip notu: Giriş uzamış, pullback gerekli." in text
