from __future__ import annotations

from bist_core.services import advisor as advisor_mod
from bist_core.services.advisor_chat_service import build_advisor_chat_service_result
from bist_core.services.advisor_chat_runtime import build_chat_result_via_advisor
from bist_core.services.live_price_sanity import sanitize_chat_result_live_text


KNOWN = ["ASELS", "AKBNK", "GARAN", "THYAO", "TUPRS", "EREGL"]


def test_sanitize_chat_result_live_text_sets_structured_suppression_meta() -> None:
    got = sanitize_chat_result_live_text(
        {
            "text": (
                "ASELS | score=1.48. Canlı bağlam: Canlı fiyat (01) 330.0; "
                "entry gap +650.34%; Canlı/EOD farkı +0.00%."
            )
        }
    )
    assert got["live_context_meta"]["suppressed"] is True
    assert got["live_context_meta"]["suppression_reason"] == "suspicious_live_gap_text"
    assert "330.0" not in got["text"]


def test_build_chat_result_via_advisor_surfaces_live_context_meta_when_suppressed() -> None:
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
    assert got["live_context_meta"]["suppressed"] is True
    assert got["live_context_meta"]["suppression_reason"] == "live_price_out_of_band"
    assert got["live_context_meta"]["suppressed_symbols"] == ["ASELS"]
    assert got["live_context_meta"]["suppression_reasons"] == ["live_price_out_of_band"]
    assert "330.0" not in got["text"]
    assert "Canlı veri ölçek tutarsızlığı nedeniyle canlı bağlam gizlendi." in got["text"]
    assert got["text"].count("Canlı veri ölçek tutarsızlığı nedeniyle canlı bağlam gizlendi.") == 1


def test_build_advisor_chat_service_result_passthroughs_live_context_meta_to_quality() -> None:
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
        got = build_advisor_chat_service_result(
            text="ASELS için giriş kaçtı mı?",
            day="2026-03-14",
            known_symbols=KNOWN,
            scan_universe=["ASELS", "AKBNK", "GARAN"],
        )
    finally:
        advisor_mod.build_advice_for_symbol = original

    assert got["ok"] is True
    assert got["live_context_meta"]["suppressed"] is True
    assert got["live_context_meta"]["suppression_reason"] == "live_price_out_of_band"
    assert got["live_context_meta"]["suppressed_symbols"] == ["ASELS"]
    assert got["quality"]["has_live_context_suppressed"] is True
    assert got["quality"]["live_context_suppression_reason"] == "live_price_out_of_band"
    assert got["quality"]["route_quality_ok"] is True
