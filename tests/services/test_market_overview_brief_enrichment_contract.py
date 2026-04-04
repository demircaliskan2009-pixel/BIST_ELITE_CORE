from __future__ import annotations

from bist_core.services.market_overview_brief import build_market_overview_brief


def test_build_market_overview_brief_adds_leader_gap_and_theme() -> None:
    got = build_market_overview_brief(
        [
            {
                "symbol": "AKBNK",
                "score": 4.4,
                "decision": "buy",
                "is_discount_to_entry": True,
                "rationale": "Banka momentumu daha güçlü.",
            },
            {
                "symbol": "GARAN",
                "score": 3.7,
                "decision": "watch",
                "entry_missed": True,
                "rationale": "Fiyat uzadığı için ikinci sırada.",
            },
            {
                "symbol": "ASELS",
                "score": 3.1,
                "decision": "hold",
                "rationale": "Savunma teması korunuyor.",
            },
        ],
        top_n=3,
    )

    assert "Piyasada öne çıkan lider AKBNK (score=4.40)." in got
    assert "En yakın rakip GARAN; fark +0.70." in got
    assert "Lider görünüm: girişe göre indirimli, karar=buy." in got
    assert "Öne çıkanlar: AKBNK, GARAN, ASELS." in got
    assert "Lider tema: Banka momentumu daha güçlü." in got
