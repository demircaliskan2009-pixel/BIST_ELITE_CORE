from __future__ import annotations

from bist_core.services import advisor as advisor_mod
from bist_core.services.advisor_chat_service import (
    build_advisor_chat_service_result,
    normalize_advisor_chat_request,
    render_advisor_chat_markdown,
    render_advisor_chat_text,
)


KNOWN = ["ASELS", "AKBNK", "GARAN", "THYAO", "TUPRS", "EREGL"]


def test_normalize_advisor_chat_request_coerces_fields_and_extra_kwargs() -> None:
    got = normalize_advisor_chat_request(
        {
            "query": "scan top 2",
            "date": "2026-03-14",
            "known_symbols": "ASELS AKBNK GARAN",
            "scan_universe": ["AKBNK", "GARAN", "ASELS"],
            "default_scan_n": "3",
            "root_path": "demo-root",
        }
    )
    assert got["text"] == "scan top 2"
    assert got["day"] == "2026-03-14"
    assert got["known_symbols"] == ["ASELS", "AKBNK", "GARAN"]
    assert got["scan_universe"] == ["AKBNK", "GARAN", "ASELS"]
    assert got["default_scan_n"] == 3
    assert got["advisor_kwargs"] == {"root_path": "demo-root"}


def test_build_advisor_chat_service_result_scan_contract() -> None:
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
    assert got["leader_symbol"] == "AKBNK"
    assert got["advisor_count"] == 3
    assert got["advisor_error_count"] == 0
    assert "1) AKBNK" in got["text"]


def test_build_advisor_chat_service_result_comparison_contract() -> None:
    original = advisor_mod.build_advice_for_symbol

    def fake_build_advice_for_symbol(symbol, date):
        payload = {
            "AKBNK": {"symbol": "AKBNK", "decision": "buy", "score": 3.9},
            "GARAN": {"symbol": "GARAN", "decision": "buy", "score": 4.2},
        }
        return payload[symbol]

    advisor_mod.build_advice_for_symbol = fake_build_advice_for_symbol
    try:
        got = build_advisor_chat_service_result(
            {
                "text": "AKBNK ile GARAN karşılaştır",
                "day": "2026-03-14",
                "known_symbols": KNOWN,
                "scan_universe": ["AKBNK", "GARAN", "ASELS"],
            }
        )
    finally:
        advisor_mod.build_advice_for_symbol = original

    assert got["ok"] is True
    assert got["route"] == "comparison"
    assert got["leader_symbol"] == "GARAN"
    assert got["resolved_symbols"] == ["AKBNK", "GARAN"]
    assert "GARAN önde" in got["text"]


def test_build_advisor_chat_service_result_single_symbol_contract() -> None:
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
        got = build_advisor_chat_service_result(
            {
                "message": "ASELS için giriş kaçtı mı?",
                "day": "2026-03-14",
                "known_symbols": KNOWN,
                "scan_universe": ["AKBNK", "GARAN", "ASELS"],
            }
        )
    finally:
        advisor_mod.build_advice_for_symbol = original

    assert got["ok"] is True
    assert got["route"] == "single_symbol"
    assert got["primary_symbol"] == "ASELS"
    assert got["resolved_symbols"] == ["ASELS"]
    assert "+2.32%" in got["text"]


def test_build_advisor_chat_service_result_partial_failure_exposes_error_map() -> None:
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
    assert got["advisor_count"] == 2
    assert got["advisor_error_count"] == 1
    assert got["advisor_errors"] == {"GARAN": "RuntimeError"}
    assert "1) AKBNK" in got["text"]
    assert "2) ASELS" in got["text"]


def test_render_advisor_chat_text_returns_text() -> None:
    original = advisor_mod.build_advice_for_symbol

    def fake_build_advice_for_symbol(symbol, date):
        payload = {
            "AKBNK": {"symbol": "AKBNK", "decision": "buy", "score": 4.4},
            "GARAN": {"symbol": "GARAN", "decision": "watch", "score": 3.7, "entry_missed": True},
        }
        return payload[symbol]

    advisor_mod.build_advice_for_symbol = fake_build_advice_for_symbol
    try:
        got = render_advisor_chat_text(
            text="AKBNK ile GARAN karşılaştır",
            day="2026-03-14",
            known_symbols=KNOWN,
            scan_universe=["AKBNK", "GARAN"],
        )
    finally:
        advisor_mod.build_advice_for_symbol = original

    assert "AKBNK önde" in got
    assert "GARAN" in got


def test_render_advisor_chat_markdown_returns_markdown() -> None:
    original = advisor_mod.build_advice_for_symbol

    def fake_build_advice_for_symbol(symbol, date):
        payload = {
            "AKBNK": {"symbol": "AKBNK", "decision": "buy", "score": 4.4},
            "GARAN": {"symbol": "GARAN", "decision": "watch", "score": 3.7, "entry_missed": True},
        }
        return payload[symbol]

    advisor_mod.build_advice_for_symbol = fake_build_advice_for_symbol
    try:
        got = render_advisor_chat_markdown(
            text="AKBNK ile GARAN karşılaştır",
            day="2026-03-14",
            known_symbols=KNOWN,
            scan_universe=["AKBNK", "GARAN"],
        )
    finally:
        advisor_mod.build_advice_for_symbol = original

    assert "## AKBNK vs GARAN" in got
    assert "2 sembol | lider=AKBNK" in got
    assert "AKBNK önde" in got
