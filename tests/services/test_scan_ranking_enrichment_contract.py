from __future__ import annotations

from bist_core.services.scan_ranking import render_scan_ranking_text


def test_render_scan_ranking_text_enforces_leader_reasons_and_factor_diff() -> None:
    got = render_scan_ranking_text(
        [
            {
                "symbol": "AKBNK",
                "score": 4.4,
                "decision": "buy",
                "is_discount_to_entry": True,
                "rationale": "Banka momentumu ve giriş disiplini daha iyi.",
                "live_gap_pct": 0.9,
            },
            {
                "symbol": "GARAN",
                "score": 3.8,
                "decision": "watch",
                "entry_missed": True,
                "rationale": "Fiyat uzamış, yeni giriş için zayıf.",
                "live_gap_pct": 3.6,
            },
        ],
        top_n=2,
    )

    assert "AKBNK lider" in got
    assert "Neden AKBNK lider:" in got
    assert "Rakip baskısı:" in got
    assert "Faktör farkları:" in got
    assert "skor | AKBNK=4.40 | GARAN=3.80 | fark=+0.60" in got
    assert "giriş durumu | AKBNK=girişe göre indirimli | GARAN=giriş kaçmış" in got
    assert "Lider notu: Banka momentumu ve giriş disiplini daha iyi." in got
    assert "Yakın rakip notu: Fiyat uzamış, yeni giriş için zayıf." in got
