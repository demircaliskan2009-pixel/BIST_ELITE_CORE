from __future__ import annotations

from bist_core.services.symbol_comparison import render_comparison_text


def test_render_comparison_text_enforces_dual_rationale_and_factor_diff() -> None:
    got = render_comparison_text(
        [
            {
                "symbol": "AKBNK",
                "score": 3.9,
                "decision": "buy",
                "entry_missed": True,
                "rationale": "Giriş uzamış, pullback gerekli.",
                "live_gap_pct": 3.4,
            },
            {
                "symbol": "GARAN",
                "score": 4.2,
                "decision": "buy",
                "is_discount_to_entry": True,
                "rationale": "Relatif güç ve banka teması daha dengeli.",
                "live_gap_pct": 0.8,
            },
        ]
    )

    assert "GARAN önde" in got
    assert "Neden GARAN önde:" in got
    assert "Neden AKBNK geride:" in got
    assert "Faktör farkları:" in got
    assert "skor | GARAN=4.20 | AKBNK=3.90 | fark=+0.30" in got
    assert "giriş durumu | GARAN=girişe göre indirimli | AKBNK=giriş kaçmış" in got
    assert "Lider notu: Relatif güç ve banka teması daha dengeli." in got
    assert "Rakip notu: Giriş uzamış, pullback gerekli." in got
