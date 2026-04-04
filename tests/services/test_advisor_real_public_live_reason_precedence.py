from __future__ import annotations

from bist_core.services import advisor as advisor_mod


KNOWN = ["ASELS", "AKBNK", "GARAN", "THYAO", "TUPRS", "EREGL"]


def test_real_public_entrypoint_prefers_payload_reason_over_text_sanitizer_reason() -> None:
    got = advisor_mod.build_chat_response_for_text(
        "ASELS için giriş kaçtı mı?",
        "2026-03-14",
        known_symbols=KNOWN,
        scan_universe=KNOWN,
    )

    assert got["ok"] is True
    assert got["route"] == "single_symbol"
    assert got["live_context_meta"]["suppressed"] is True
    assert got["live_context_meta"]["suppression_reason"] == "live_price_out_of_band"
    assert got["quality"]["has_live_context_suppressed"] is True
    assert got["quality"]["live_context_suppression_reason"] == "live_price_out_of_band"
    assert "Canlı veri ölçek tutarsızlığı nedeniyle canlı bağlam gizlendi." in got["text"]
    assert "Sebep: suspicious_live_gap_text." not in got["text"]
