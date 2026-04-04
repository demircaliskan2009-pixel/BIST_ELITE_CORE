from __future__ import annotations

from bist_core.services import advisor as advisor_mod
from bist_core.services.advisor_chat_runtime import (
    _call_build_advice_for_symbol,
    _resolve_runtime_symbols,
    build_advice_collection_via_advisor,
    build_advice_map_via_advisor,
    build_chat_result_via_advisor,
)


KNOWN = ["ASELS", "AKBNK", "GARAN", "THYAO", "TUPRS", "EREGL"]


def test_resolve_runtime_symbols_single_symbol_uses_intent_symbols() -> None:
    intent, symbols = _resolve_runtime_symbols(
        "ASELS için giriş kaçtı mı?",
        known_symbols=KNOWN,
        scan_universe=["AKBNK", "GARAN", "ASELS"],
    )
    assert intent["intent"] == "single_symbol"
    assert symbols == ["ASELS"]


def test_resolve_runtime_symbols_scan_uses_universe() -> None:
    intent, symbols = _resolve_runtime_symbols(
        "scan top 2",
        known_symbols=KNOWN,
        scan_universe=["AKBNK", "GARAN", "ASELS"],
    )
    assert intent["intent"] == "scan"
    assert symbols == ["AKBNK", "GARAN", "ASELS"]


def test_call_build_advice_for_symbol_filters_kwargs_by_signature() -> None:
    original = advisor_mod.build_advice_for_symbol
    captured = {}

    def fake_build_advice_for_symbol(symbol, date, root_path=None):
        captured["symbol"] = symbol
        captured["date"] = date
        captured["root_path"] = root_path
        return {"symbol": symbol, "score": 1.0, "decision": "watch"}

    advisor_mod.build_advice_for_symbol = fake_build_advice_for_symbol
    try:
        got = _call_build_advice_for_symbol("ASELS", "2026-03-14", root_path="demo-root", ignored_value="x")
    finally:
        advisor_mod.build_advice_for_symbol = original

    assert got["symbol"] == "ASELS"
    assert captured == {"symbol": "ASELS", "date": "2026-03-14", "root_path": "demo-root"}


def test_build_advice_map_via_advisor_calls_each_symbol_once() -> None:
    original = advisor_mod.build_advice_for_symbol
    calls = []

    def fake_build_advice_for_symbol(symbol, date):
        calls.append((symbol, date))
        return {"symbol": symbol, "score": 1.0 if symbol == "ASELS" else 2.0, "decision": "watch"}

    advisor_mod.build_advice_for_symbol = fake_build_advice_for_symbol
    try:
        got = build_advice_map_via_advisor(["ASELS", "AKBNK"], "2026-03-14")
    finally:
        advisor_mod.build_advice_for_symbol = original

    assert list(got.keys()) == ["ASELS", "AKBNK"]
    assert calls == [("ASELS", "2026-03-14"), ("AKBNK", "2026-03-14")]


def test_build_advice_collection_via_advisor_skips_symbol_errors() -> None:
    original = advisor_mod.build_advice_for_symbol
    calls = []

    def fake_build_advice_for_symbol(symbol, date):
        calls.append(symbol)
        if symbol == "GARAN":
            raise RuntimeError("boom")
        return {"symbol": symbol, "score": 1.0, "decision": "watch"}

    advisor_mod.build_advice_for_symbol = fake_build_advice_for_symbol
    try:
        got = build_advice_collection_via_advisor(["AKBNK", "GARAN", "ASELS"], "2026-03-14")
    finally:
        advisor_mod.build_advice_for_symbol = original

    assert calls == ["AKBNK", "GARAN", "ASELS"]
    assert list(got["advice_map"].keys()) == ["AKBNK", "ASELS"]
    assert got["errors"] == {"GARAN": "RuntimeError"}
    assert got["requested_symbols"] == ["AKBNK", "GARAN", "ASELS"]


def test_build_chat_result_via_advisor_single_symbol_contract() -> None:
    original = advisor_mod.build_advice_for_symbol

    def fake_build_advice_for_symbol(symbol, date):
        return {
            "symbol": symbol,
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
    assert got["route"] == "single_symbol"
    assert got["primary_symbol"] == "ASELS"
    assert got["resolved_symbols"] == ["ASELS"]
    assert got["advisor_count"] == 1
    assert got["advisor_error_count"] == 0
    assert "giriş kaçmış" in got["text"]
    assert "+2.32%" in got["text"]


def test_build_chat_result_via_advisor_comparison_contract() -> None:
    original = advisor_mod.build_advice_for_symbol

    def fake_build_advice_for_symbol(symbol, date):
        score_map = {"AKBNK": 3.9, "GARAN": 4.2, "ASELS": 9.9}
        return {"symbol": symbol, "decision": "buy", "score": score_map[symbol]}

    advisor_mod.build_advice_for_symbol = fake_build_advice_for_symbol
    try:
        got = build_chat_result_via_advisor(
            "AKBNK ile GARAN karşılaştır",
            "2026-03-14",
            known_symbols=KNOWN,
            scan_universe=["ASELS", "AKBNK", "GARAN"],
        )
    finally:
        advisor_mod.build_advice_for_symbol = original

    assert got["ok"] is True
    assert got["route"] == "comparison"
    assert got["leader_symbol"] == "GARAN"
    assert got["resolved_symbols"] == ["AKBNK", "GARAN"]
    assert got["advisor_count"] == 2
    assert "GARAN önde" in got["text"]


def test_build_chat_result_via_advisor_scan_contract() -> None:
    original = advisor_mod.build_advice_for_symbol

    def fake_build_advice_for_symbol(symbol, date):
        payload = {
            "AKBNK": {"symbol": "AKBNK", "decision": "buy", "score": 4.4},
            "GARAN": {"symbol": "GARAN", "decision": "watch", "score": 3.7, "entry_missed": True},
            "ASELS": {"symbol": "ASELS", "decision": "hold", "score": 3.1},
        }
        return payload[symbol]

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
    assert got["leader_symbol"] == "AKBNK"
    assert got["resolved_symbols"] == ["AKBNK", "GARAN", "ASELS"]
    assert got["advisor_count"] == 3
    assert "1) AKBNK" in got["text"]
    assert "2) GARAN" in got["text"]


def test_build_chat_result_via_advisor_scan_survives_partial_symbol_failure() -> None:
    original = advisor_mod.build_advice_for_symbol

    def fake_build_advice_for_symbol(symbol, date):
        payload = {
            "AKBNK": {"symbol": "AKBNK", "decision": "buy", "score": 4.4},
            "GARAN": RuntimeError("boom"),
            "ASELS": {"symbol": "ASELS", "decision": "buy", "score": 4.0, "rationale": "Momentum güçlü"},
        }
        item = payload[symbol]
        if isinstance(item, Exception):
            raise item
        return item

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
    assert got["advisor_count"] == 2
    assert got["advisor_error_count"] == 1
    assert got["advisor_errors"] == {"GARAN": "RuntimeError"}
    assert "1) AKBNK" in got["text"]
    assert "2) ASELS" in got["text"]


def test_build_chat_result_via_advisor_single_symbol_surfaces_missing_result_when_advisor_fails() -> None:
    original = advisor_mod.build_advice_for_symbol

    def fake_build_advice_for_symbol(symbol, date):
        raise RuntimeError("boom")

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

    assert got["ok"] is False
    assert got["route"] == "single_symbol"
    assert got["advisor_count"] == 0
    assert got["advisor_error_count"] == 1
    assert got["advisor_errors"] == {"ASELS": "RuntimeError"}
    assert got["resolved_symbols"] == ["ASELS"]
    assert "İstenen sembol için sonuç bulunamadı." in got["text"]


def test_build_chat_result_via_advisor_market_overview_contract() -> None:
    original = advisor_mod.build_advice_for_symbol

    def fake_build_advice_for_symbol(symbol, date):
        payload = {
            "AKBNK": {"symbol": "AKBNK", "decision": "buy", "score": 4.4},
            "GARAN": {"symbol": "GARAN", "decision": "watch", "score": 3.7, "entry_missed": True},
            "ASELS": {"symbol": "ASELS", "decision": "hold", "score": 3.1},
        }
        return payload[symbol]

    advisor_mod.build_advice_for_symbol = fake_build_advice_for_symbol
    try:
        got = build_chat_result_via_advisor(
            "BIST genel görünüm ne durumda?",
            "2026-03-14",
            known_symbols=KNOWN,
            scan_universe=["AKBNK", "GARAN", "ASELS"],
        )
    finally:
        advisor_mod.build_advice_for_symbol = original

    assert got["ok"] is True
    assert got["route"] == "market_overview"
    assert got["leader_symbol"] == "AKBNK"
    assert got["resolved_symbols"] == ["AKBNK", "GARAN", "ASELS"]
    assert got["advisor_count"] == 3
    assert "Öne çıkanlar" in got["text"]
