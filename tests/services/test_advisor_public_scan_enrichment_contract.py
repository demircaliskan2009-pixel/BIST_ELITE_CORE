from __future__ import annotations

from bist_core.services import advisor as advisor_mod


KNOWN = ["ASELS", "AKBNK", "GARAN", "THYAO", "TUPRS", "EREGL"]


def test_public_scan_route_preserves_leader_detail_and_factor_diff() -> None:
    original = advisor_mod.build_advice_for_symbol

    def fake_build_advice_for_symbol(symbol, date):
        payload = {
            "AKBNK": {
                "symbol": "AKBNK",
                "decision": "buy",
                "score": 4.4,
                "is_discount_to_entry": True,
                "compact_rationale": "Banka momentumu ve giriş disiplini daha iyi.",
                "live_gap_pct": 0.9,
            },
            "GARAN": {
                "symbol": "GARAN",
                "decision": "watch",
                "score": 3.8,
                "entry_missed": True,
                "compact_rationale": "Fiyat uzamış, yeni giriş için zayıf.",
                "live_gap_pct": 3.6,
            },
            "ASELS": {
                "symbol": "ASELS",
                "decision": "hold",
                "score": 3.1,
                "compact_rationale": "Savunma teması korunuyor.",
                "live_gap_pct": 1.2,
            },
        }
        return payload[symbol]

    advisor_mod.build_advice_for_symbol = fake_build_advice_for_symbol
    try:
        got = advisor_mod.build_chat_response_for_text(
            "scan top 2",
            "2026-03-14",
            known_symbols=KNOWN,
            scan_universe=["AKBNK", "GARAN", "ASELS"],
        )
    finally:
        advisor_mod.build_advice_for_symbol = original

    assert got["ok"] is True
    assert got["route"] == "scan"
    assert got["leader_symbol"] == "AKBNK"

    text = got["text"]
    assert "AKBNK lider" in text
    assert "Neden AKBNK lider:" in text
    assert "Rakip baskısı:" in text
    assert "Faktör farkları:" in text
    assert "Lider notu: Banka momentumu ve giriş disiplini daha iyi." in text
    assert "Yakın rakip notu: Fiyat uzamış, yeni giriş için zayıf." in text
