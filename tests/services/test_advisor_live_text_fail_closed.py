from __future__ import annotations

from bist_core.services import advisor as advisor_mod
from bist_core.services.advisor_chat_runtime import build_chat_result_via_advisor
from bist_core.services.live_price_sanity import (
    sanitize_advice_payload_for_chat,
    sanitize_chat_result_live_text,
    sanitize_live_text_for_chat,
)


KNOWN = ["ASELS", "AKBNK", "GARAN", "THYAO", "TUPRS", "EREGL"]


def test_sanitize_live_text_for_chat_strips_suspicious_gap_block() -> None:
    text = (
        "ASELS için karar BUY; skor 1.48.\n\n"
        "İşlem planı: entry 43.98, stop 42.68, t1 44.86. "
        "Canlı bağlam: Canlı fiyat (01) 330.0; entry seviyesinin üzerinde; "
        "plan kovalanmamalı, geri çekilme veya yeniden teyit beklenmeli; "
        "entry gap +650.34%; Canlı/EOD farkı +0.00%.\n\n"
        "Olaylar (KAP/diğer):\nKAP/olay verisi yok veya erişilemedi."
    )
    got = sanitize_live_text_for_chat(text)
    assert "330.0" not in got
    assert "+650.34%" not in got
    assert "Canlı bağlam:" not in got
    assert "İşlem planı: entry 43.98" in got
    assert "Canlı veri ölçek tutarsızlığı nedeniyle canlı bağlam gizlendi." in got


def test_sanitize_live_text_for_chat_keeps_normal_gap_text() -> None:
    text = (
        "ASELS | karar=buy | score=4.00. giriş=71.00 | stop=69.50 | hedef=76.00. "
        "Momentum güçlü. Canlı fiyat girişin +2.32% üzerinde; giriş kaçmış görünüyor."
    )
    got = sanitize_live_text_for_chat(text)
    assert got == text
    assert "+2.32%" in got


def test_sanitize_advice_payload_for_chat_cleans_text_even_without_live_payload() -> None:
    got = sanitize_advice_payload_for_chat(
        {
            "symbol": "ASELS",
            "entry": 43.98,
            "stop": 42.68,
            "target": 44.86,
            "text": (
                "ASELS için karar BUY; skor 1.48. "
                "Canlı bağlam: Canlı fiyat (01) 330.0; entry gap +650.34%."
            ),
        }
    )
    assert "330.0" not in got["text"]
    assert "+650.34%" not in got["text"]
    assert "Canlı veri ölçek tutarsızlığı nedeniyle canlı bağlam gizlendi." in got["text"]


def test_sanitize_chat_result_live_text_cleans_top_level_and_preview() -> None:
    got = sanitize_chat_result_live_text(
        {
            "text": "ASELS | score=1.48. Canlı bağlam: Canlı fiyat (01) 330.0; entry gap +650.34%.",
            "preview": "Canlı fiyat (01) 330.0; entry gap +650.34%.",
        }
    )
    assert "330.0" not in got["text"]
    assert "+650.34%" not in got["text"]
    assert "330.0" not in got["preview"]


def test_build_chat_result_via_advisor_hides_suspicious_live_context_in_compact_output() -> None:
    original = advisor_mod.build_advice_for_symbol

    def fake_build_advice_for_symbol(symbol, date):
        return {
            "symbol": symbol,
            "date": "2025-12-16",
            "decision": "buy",
            "score": 1.48,
            "entry": 43.98,
            "stop": 42.68,
            "target": 44.86,
            "rationale": "Momentum pozitif",
            "live_payload": {
                "current_price": 330.0,
                "last_price": 330.0,
                "price": 330.0,
            },
        }

    advisor_mod.build_advice_for_symbol = fake_build_advice_for_symbol
    try:
        got = build_chat_result_via_advisor(
            "ASELS için giriş kaçtı mı?",
            "2026-03-14",
            known_symbols=KNOWN,
            scan_universe=["ASELS", "AKBNK", "GARAN"],
        )
    finally:
        advisor_mod.build_advice_for_symbol = original

    assert got["ok"] is True
    assert got["route"] == "single_symbol"
    assert "330.0" not in got["text"]
    assert "+650.34%" not in got["text"]
    assert "Canlı bağlam:" not in got["text"]
    assert "giriş=43.98" in got["text"]
    assert "Momentum pozitif" in got["text"]
    assert "Veri as-of: 2025-12-16" in got["text"]


def test_build_chat_result_via_advisor_keeps_normal_live_context_when_payload_is_sane() -> None:
    original = advisor_mod.build_advice_for_symbol

    def fake_build_advice_for_symbol(symbol, date):
        return {
            "symbol": symbol,
            "date": "2025-12-16",
            "decision": "buy",
            "score": 4.0,
            "entry": 71.0,
            "stop": 69.5,
            "target": 76.0,
            "rationale": "Momentum güçlü",
            "live_payload": {
                "current_price": 72.6500015258789,
                "last_price": 72.65,
                "price": 72.65,
            },
        }

    advisor_mod.build_advice_for_symbol = fake_build_advice_for_symbol
    try:
        got = build_chat_result_via_advisor(
            "ASELS için giriş kaçtı mı?",
            "2026-03-14",
            known_symbols=KNOWN,
            scan_universe=["ASELS", "AKBNK", "GARAN"],
        )
    finally:
        advisor_mod.build_advice_for_symbol = original

    assert got["ok"] is True
    assert "+2.32%" in got["text"]
    assert "Canlı fiyat girişin +2.32% üzerinde" in got["text"]
    assert "Canlı veri ölçek tutarsızlığı nedeniyle canlı bağlam gizlendi." not in got["text"]
