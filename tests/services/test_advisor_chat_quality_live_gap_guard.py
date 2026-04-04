from __future__ import annotations

from bist_core.services import advisor as advisor_mod
from bist_core.services.advisor_chat_quality import build_advisor_chat_quality_metrics
from bist_core.services.advisor_chat_service import build_advisor_chat_service_result


KNOWN = ["ASELS", "AKBNK", "GARAN", "THYAO", "TUPRS", "EREGL"]


def test_build_advisor_chat_quality_metrics_flags_unsanitized_suspicious_live_gap() -> None:
    got = build_advisor_chat_quality_metrics(
        {
            "route": "single_symbol",
            "text": (
                "ASELS | karar=buy | score=1.48. giriş=43.98 | stop=42.68 | hedef=44.86. "
                "Momentum pozitif. Canlı fiyat (01) 330.0; entry gap +650.34%; "
                "Canlı/EOD farkı +0.00%."
            ),
            "title": "ASELS Özeti",
            "subtitle": "Canlı giriş özeti | sembol=ASELS",
            "primary_symbol": "ASELS",
            "advisor_count": 1,
            "advisor_error_count": 0,
            "data_asof_mode": "fallback",
            "data_asof_requested_day": "2026-03-14",
            "data_asof_effective_days": ["2026-03-03"],
            "data_asof_symbols": ["ASELS"],
            "response": {
                "response": {
                    "symbols": {
                        "requested": ["ASELS"],
                        "requested_symbol": "ASELS",
                        "primary": "ASELS",
                        "leader": None,
                    },
                    "metrics": {
                        "top_n": None,
                        "scan_count": 0,
                        "comparison_count": 0,
                    },
                }
            },
        }
    )
    assert got["entry_gap_pct"] == 650.34
    assert got["has_suspicious_live_gap"] is True
    assert got["has_live_scale_warning"] is False
    assert got["route_quality_ok"] is False


def test_build_advisor_chat_quality_metrics_accepts_sanitized_live_scale_warning() -> None:
    got = build_advisor_chat_quality_metrics(
        {
            "route": "single_symbol",
            "text": (
                "ASELS | karar=buy | score=1.48. giriş=43.98 | stop=42.68 | hedef=44.86. "
                "Momentum pozitif.\n\n"
                "Canlı veri ölçek tutarsızlığı nedeniyle canlı bağlam gizlendi.\n\n"
                "Veri as-of: 2026-03-03 (istenen gün: 2026-03-14; fallback semboller: ASELS)."
            ),
            "title": "ASELS Özeti",
            "subtitle": "Canlı giriş özeti | sembol=ASELS | as-of=2026-03-03",
            "primary_symbol": "ASELS",
            "advisor_count": 1,
            "advisor_error_count": 0,
            "data_asof_mode": "fallback",
            "data_asof_requested_day": "2026-03-14",
            "data_asof_effective_days": ["2026-03-03"],
            "data_asof_symbols": ["ASELS"],
            "response": {
                "response": {
                    "symbols": {
                        "requested": ["ASELS"],
                        "requested_symbol": "ASELS",
                        "primary": "ASELS",
                        "leader": None,
                    },
                    "metrics": {
                        "top_n": None,
                        "scan_count": 0,
                        "comparison_count": 0,
                    },
                }
            },
        }
    )
    assert got["entry_gap_pct"] is None
    assert got["has_suspicious_live_gap"] is False
    assert got["has_live_scale_warning"] is True
    assert got["has_asof_fallback"] is True
    assert got["route_quality_ok"] is True


def test_build_advisor_chat_service_result_keeps_quality_green_with_bad_live_payload_safely_removed() -> None:
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
    assert got["route"] == "single_symbol"
    assert got["quality"]["has_suspicious_live_gap"] is False
    assert got["quality"]["route_quality_ok"] is True
    assert "330.0" not in got["text"]
    assert "+650.34%" not in got["text"]
