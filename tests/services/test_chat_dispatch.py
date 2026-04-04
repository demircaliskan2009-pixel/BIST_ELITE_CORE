from __future__ import annotations

from bist_core.services.chat_dispatch import (
    build_chat_dispatch_plan,
    dispatch_chat_request,
)


KNOWN = ["ASELS", "AKBNK", "GARAN", "THYAO", "TUPRS", "EREGL"]


def test_build_chat_dispatch_plan_scan() -> None:
    got = build_chat_dispatch_plan("scan top 5", known_symbols=KNOWN)
    assert got["route"] == "scan"
    assert got["top_n"] == 5
    assert got["error_code"] is None


def test_build_chat_dispatch_plan_comparison() -> None:
    got = build_chat_dispatch_plan("AKBNK ile GARAN karşılaştır", known_symbols=KNOWN)
    assert got["route"] == "comparison"
    assert got["symbols"] == ["AKBNK", "GARAN"]
    assert got["error_code"] is None


def test_dispatch_chat_request_comparison_uses_requested_symbols_only() -> None:
    got = dispatch_chat_request(
        "AKBNK ile GARAN karşılaştır",
        known_symbols=KNOWN,
        results_by_symbol={
            "AKBNK": {"symbol": "AKBNK", "score": 3.9, "decision": "buy"},
            "GARAN": {"symbol": "GARAN", "score": 4.2, "decision": "buy"},
            "ASELS": {"symbol": "ASELS", "score": 9.9, "decision": "buy"},
        },
    )
    assert got["route"] == "comparison"
    assert got["ok"] is True
    assert got["symbols"] == ["AKBNK", "GARAN"]
    assert got["payload"]["leader"]["symbol"] == "GARAN"
    assert "GARAN önde" in got["text"]


def test_dispatch_chat_request_comparison_fails_when_only_one_result_exists() -> None:
    got = dispatch_chat_request(
        "AKBNK ile GARAN karşılaştır",
        known_symbols=KNOWN,
        results_by_symbol={
            "AKBNK": {"symbol": "AKBNK", "score": 3.9, "decision": "buy"},
        },
    )
    assert got["route"] == "comparison"
    assert got["ok"] is False
    assert got["error_code"] == "insufficient_comparison_results"


def test_dispatch_chat_request_scan_returns_ranked_text() -> None:
    got = dispatch_chat_request(
        "scan top 2",
        known_symbols=KNOWN,
        scan_results=[
            {"symbol": "AKBNK", "score": 4.4, "decision": "buy", "entry_missed": False},
            {"symbol": "GARAN", "score": 3.7, "decision": "watch", "entry_missed": True},
            {"symbol": "ASELS", "score": 3.1, "decision": "hold", "entry_missed": False},
        ],
    )
    assert got["route"] == "scan"
    assert got["ok"] is True
    assert got["top_n"] == 2
    assert got["payload"]["symbols"] == ["AKBNK", "GARAN"]
    assert "1) AKBNK" in got["text"]
    assert "2) GARAN" in got["text"]


def test_dispatch_chat_request_single_symbol_selects_exact_symbol_and_renders_text() -> None:
    got = dispatch_chat_request(
        "ASELS için giriş kaçtı mı?",
        known_symbols=KNOWN,
        results_by_symbol={
            "ASELS": {
                "symbol": "ASELS",
                "score": 4.0,
                "decision": "buy",
                "entry": 71.0,
                "stop": 69.5,
                "target": 76.0,
                "rationale": "Momentum güçlü",
                "live_payload": {
                    "current_price": 72.6500015258789,
                    "last_price": 72.65,
                    "price": 72.65,
                },
            },
            "AKBNK": {"symbol": "AKBNK", "score": 4.9, "decision": "buy"},
        },
    )
    assert got["route"] == "single_symbol"
    assert got["ok"] is True
    assert got["symbols"] == ["ASELS"]
    assert got["payload"]["symbol"] == "ASELS"
    assert "ASELS" in got["text"]
    assert "giriş kaçmış" in got["text"]
    assert "hedef=76.00" in got["text"]


def test_dispatch_chat_request_market_overview_is_not_forced_to_symbol() -> None:
    got = dispatch_chat_request(
        "BIST genel görünüm ve sektör rotasyonu ne durumda?",
        known_symbols=KNOWN,
        results_by_symbol={
            "ASELS": {"symbol": "ASELS", "score": 4.0, "decision": "buy"},
        },
    )
    assert got["route"] == "market_overview"
    assert got["ok"] is True
    assert got["symbols"] == []
