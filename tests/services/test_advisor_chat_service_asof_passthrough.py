from __future__ import annotations

from bist_core.services import advisor as advisor_mod
from bist_core.services.advisor_chat_service import build_advisor_chat_service_result


KNOWN = ["ASELS", "AKBNK", "GARAN", "THYAO", "TUPRS", "EREGL"]


def test_build_advisor_chat_service_result_exact_asof_passthrough() -> None:
    original = advisor_mod.build_advice_for_symbol

    def fake_build_advice_for_symbol(symbol, date):
        return {
            "symbol": symbol,
            "date": "2026-03-14",
            "decision": "buy",
            "score": 4.0,
            "entry": 71.0,
            "stop": 69.5,
            "target": 76.0,
            "rationale": "Momentum güçlü",
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
    assert got["data_asof_mode"] == "exact"
    assert got["data_asof_requested_day"] == "2026-03-14"
    assert got["data_asof_effective_days"] == ["2026-03-14"]
    assert got["data_asof_symbols"] == []
    assert got["quality"]["data_asof_mode"] == "exact"
    assert got["quality"]["has_asof_fallback"] is False


def test_build_advisor_chat_service_result_fallback_asof_passthrough() -> None:
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
    assert got["data_asof_mode"] == "fallback"
    assert got["data_asof_requested_day"] == "2026-03-14"
    assert got["data_asof_effective_days"] == ["2025-12-16"]
    assert got["data_asof_symbols"] == ["ASELS"]
    assert "Veri as-of: 2025-12-16" in got["text"]
    assert got["quality"]["data_asof_mode"] == "fallback"
    assert got["quality"]["has_asof_fallback"] is True
    assert got["quality"]["has_asof_note"] is True


def test_build_advisor_chat_service_result_scan_fallback_asof_passthrough() -> None:
    original = advisor_mod.build_advice_for_symbol

    def fake_build_advice_for_symbol(symbol, date):
        score_map = {"AKBNK": 4.4, "GARAN": 3.7, "ASELS": 3.1}
        return {
            "symbol": symbol,
            "date": "2025-12-16",
            "decision": "buy" if symbol == "AKBNK" else "watch",
            "score": score_map[symbol],
        }

    advisor_mod.build_advice_for_symbol = fake_build_advice_for_symbol
    try:
        got = build_advisor_chat_service_result(
            text="scan top 2",
            day="2026-03-14",
            known_symbols=KNOWN,
            scan_universe=["AKBNK", "GARAN", "ASELS"],
        )
    finally:
        advisor_mod.build_advice_for_symbol = original

    assert got["ok"] is True
    assert got["route"] == "scan"
    assert got["data_asof_mode"] == "fallback"
    assert got["data_asof_effective_days"] == ["2025-12-16"]
    assert got["data_asof_symbols"] == ["AKBNK", "GARAN", "ASELS"]
    assert got["quality"]["data_asof_mode"] == "fallback"
    assert got["quality"]["has_asof_fallback"] is True
