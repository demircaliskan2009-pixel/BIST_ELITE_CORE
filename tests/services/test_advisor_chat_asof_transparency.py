from __future__ import annotations

from bist_core.services import advisor as advisor_mod
from bist_core.services.advisor_chat_runtime import build_chat_result_via_advisor


KNOWN = ["ASELS", "AKBNK", "GARAN", "THYAO", "TUPRS", "EREGL"]


def test_build_chat_result_via_advisor_marks_exact_mode_when_dates_match() -> None:
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
    assert got["data_asof_mode"] == "exact"
    assert got["data_asof_effective_days"] == ["2026-03-14"]
    assert "Veri as-of:" not in got["text"]


def test_build_chat_result_via_advisor_appends_asof_note_for_single_symbol_fallback() -> None:
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
    assert got["data_asof_mode"] == "fallback"
    assert got["data_asof_requested_day"] == "2026-03-14"
    assert got["data_asof_effective_days"] == ["2025-12-16"]
    assert got["data_asof_symbols"] == ["ASELS"]
    assert "Veri as-of: 2025-12-16" in got["text"]
    assert "fallback semboller: ASELS" in got["text"]


def test_build_chat_result_via_advisor_appends_asof_note_for_scan_fallback() -> None:
    original = advisor_mod.build_advice_for_symbol

    def fake_build_advice_for_symbol(symbol, date):
        date_map = {
            "AKBNK": "2025-12-16",
            "GARAN": "2025-12-16",
            "ASELS": "2025-12-16",
        }
        score_map = {"AKBNK": 4.4, "GARAN": 3.7, "ASELS": 3.1}
        return {
            "symbol": symbol,
            "date": date_map[symbol],
            "decision": "buy" if symbol == "AKBNK" else "watch",
            "score": score_map[symbol],
        }

    advisor_mod.build_advice_for_symbol = fake_build_advice_for_symbol
    try:
        got = build_chat_result_via_advisor(
            "scan top 2",
            "2026-03-14",
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
    assert "Veri as-of: 2025-12-16" in got["text"]
    assert "fallback semboller: AKBNK, GARAN, ASELS" in got["text"]


def test_build_chat_result_via_advisor_partial_failure_keeps_asof_note_for_survivors() -> None:
    original = advisor_mod.build_advice_for_symbol

    def fake_build_advice_for_symbol(symbol, date):
        if symbol == "GARAN":
            raise RuntimeError("boom")
        return {
            "symbol": symbol,
            "date": "2025-12-16",
            "decision": "buy",
            "score": 4.4 if symbol == "AKBNK" else 4.0,
            "rationale": "Momentum güçlü",
        }

    advisor_mod.build_advice_for_symbol = fake_build_advice_for_symbol
    try:
        got = build_chat_result_via_advisor(
            "scan top 2",
            "2026-03-14",
            known_symbols=KNOWN,
            scan_universe=["AKBNK", "GARAN", "ASELS"],
        )
    finally:
        advisor_mod.build_advice_for_symbol = original

    assert got["ok"] is True
    assert got["advisor_error_count"] == 1
    assert got["advisor_errors"] == {"GARAN": "RuntimeError"}
    assert got["data_asof_mode"] == "fallback"
    assert got["data_asof_symbols"] == ["AKBNK", "ASELS"]
    assert "Veri as-of: 2025-12-16" in got["text"]
