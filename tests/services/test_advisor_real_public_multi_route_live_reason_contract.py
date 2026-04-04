from __future__ import annotations

from bist_core.services import advisor as advisor_mod


KNOWN = ["ASELS", "AKBNK", "GARAN", "THYAO", "TUPRS", "EREGL"]


def test_real_public_routes_keep_payload_reason_for_live_suppression() -> None:
    cases = [
        ("ASELS için giriş kaçtı mı?", "single_symbol", ["ASELS"]),
        ("scan top 3", "scan", ["ASELS", "AKBNK"]),
        ("BIST genel görünüm ne durumda?", "market_overview", ["ASELS", "AKBNK"]),
        ("ASELS ile AKBNK karşılaştır", "comparison", ["ASELS"]),
    ]

    for query, expected_route, expected_suppressed in cases:
        got = advisor_mod.build_chat_response_for_text(
            query,
            "2026-03-14",
            known_symbols=KNOWN,
            scan_universe=KNOWN,
        )

        assert got["ok"] is True, query
        assert got["route"] == expected_route, query

        meta = dict(got.get("live_context_meta") or {})
        quality = dict(got.get("quality") or {})
        text = str(got.get("text") or "")

        assert meta.get("suppressed") is True, query
        assert meta.get("suppression_reason") == "live_price_out_of_band", query
        assert meta.get("suppressed_symbols") == expected_suppressed, query
        assert meta.get("suppression_reasons") == ["live_price_out_of_band"], query

        assert quality.get("has_live_context_suppressed") is True, query
        assert quality.get("live_context_suppression_reason") == "live_price_out_of_band", query

        assert "Canlı veri ölçek tutarsızlığı nedeniyle canlı bağlam gizlendi." in text, query
        assert "Sebep: suspicious_live_gap_text." not in text, query
        assert "330.0" not in text, query
        assert "entry gap +650.34%" not in text, query
