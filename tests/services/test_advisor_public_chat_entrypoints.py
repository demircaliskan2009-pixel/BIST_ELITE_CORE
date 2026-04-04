from __future__ import annotations

from bist_core.services import advisor as advisor_mod


KNOWN = ["ASELS", "AKBNK", "GARAN", "THYAO", "TUPRS", "EREGL"]


def test_build_chat_response_for_text_scan_contract() -> None:
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
        got = advisor_mod.build_chat_response_for_text(
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
    assert got["advisor_count"] == 3
    assert "1) AKBNK" in got["text"]


def test_build_chat_response_for_text_single_symbol_contract() -> None:
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
        got = advisor_mod.build_chat_response_for_text(
            "ASELS için giriş kaçtı mı?",
            "2026-03-14",
            known_symbols=KNOWN,
            scan_universe=["AKBNK", "GARAN", "ASELS"],
        )
    finally:
        advisor_mod.build_advice_for_symbol = original

    assert got["ok"] is True
    assert got["route"] == "single_symbol"
    assert got["primary_symbol"] == "ASELS"
    assert got["resolved_symbols"] == ["ASELS"]
    assert "+2.32%" in got["text"]
    assert "giriş kaçmış" in got["text"]


def test_build_chat_response_for_text_partial_failure_remains_fail_closed() -> None:
    original = advisor_mod.build_advice_for_symbol

    def fake_build_advice_for_symbol(symbol, date):
        payload = {
            "AKBNK": {"symbol": "AKBNK", "decision": "buy", "score": 4.4},
            "GARAN": RuntimeError("boom"),
            "ASELS": {"symbol": "ASELS", "decision": "buy", "score": 4.0},
        }
        item = payload[symbol]
        if isinstance(item, Exception):
            raise item
        return item

    advisor_mod.build_advice_for_symbol = fake_build_advice_for_symbol
    try:
        got = advisor_mod.build_chat_response_for_text(
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


def test_render_chat_response_text_and_markdown_public_wrappers() -> None:
    original = advisor_mod.build_advice_for_symbol

    def fake_build_advice_for_symbol(symbol, date):
        payload = {
            "AKBNK": {"symbol": "AKBNK", "decision": "buy", "score": 4.4},
            "GARAN": {"symbol": "GARAN", "decision": "watch", "score": 3.7, "entry_missed": True},
        }
        return payload[symbol]

    advisor_mod.build_advice_for_symbol = fake_build_advice_for_symbol
    try:
        text = advisor_mod.render_chat_response_text(
            "AKBNK ile GARAN karşılaştır",
            "2026-03-14",
            known_symbols=KNOWN,
            scan_universe=["AKBNK", "GARAN"],
        )
        md = advisor_mod.render_chat_response_markdown(
            "AKBNK ile GARAN karşılaştır",
            "2026-03-14",
            known_symbols=KNOWN,
            scan_universe=["AKBNK", "GARAN"],
        )
    finally:
        advisor_mod.build_advice_for_symbol = original

    assert "AKBNK önde" in text
    assert "## AKBNK vs GARAN" in md
    assert "2 sembol | lider=AKBNK" in md
