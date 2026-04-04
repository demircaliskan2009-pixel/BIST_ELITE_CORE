from __future__ import annotations

from bist_core.services.chat_service import (
    build_chat_service_payload,
    render_chat_service_text,
)


KNOWN = ["ASELS", "AKBNK", "GARAN", "THYAO", "TUPRS", "EREGL"]


def test_build_chat_service_payload_scan_exposes_leader_and_count() -> None:
    got = build_chat_service_payload(
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
    assert got["leader_symbol"] == "AKBNK"
    assert got["primary_symbol"] == "AKBNK"
    assert got["scan_count"] == 2
    assert got["requested_symbols"] == ["AKBNK", "GARAN"]
    assert "1) AKBNK" in got["text"]


def test_build_chat_service_payload_comparison_exposes_leader_and_count() -> None:
    got = build_chat_service_payload(
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
    assert got["leader_symbol"] == "GARAN"
    assert got["primary_symbol"] == "GARAN"
    assert got["comparison_count"] == 2
    assert got["requested_symbols"] == ["AKBNK", "GARAN"]
    assert "GARAN önde" in got["text"]


def test_build_chat_service_payload_single_symbol_exposes_requested_symbol() -> None:
    got = build_chat_service_payload(
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
            }
        },
    )
    assert got["route"] == "single_symbol"
    assert got["ok"] is True
    assert got["requested_symbol"] == "ASELS"
    assert got["primary_symbol"] == "ASELS"
    assert "giriş kaçmış" in got["text"]


def test_build_chat_service_payload_market_overview_exposes_leader_from_scan_fallback() -> None:
    got = build_chat_service_payload(
        "BIST genel görünüm ne durumda?",
        known_symbols=KNOWN,
        scan_results=[
            {"symbol": "AKBNK", "score": 4.4, "decision": "buy", "entry_missed": False},
            {"symbol": "GARAN", "score": 3.7, "decision": "watch", "entry_missed": True},
            {"symbol": "ASELS", "score": 3.1, "decision": "hold", "entry_missed": False},
        ],
    )
    assert got["route"] == "market_overview"
    assert got["ok"] is True
    assert got["leader_symbol"] == "AKBNK"
    assert got["primary_symbol"] == "AKBNK"
    assert got["scan_count"] == 3
    assert "Öne çıkanlar" in got["text"]


def test_build_chat_service_payload_comparison_error_keeps_human_text() -> None:
    got = build_chat_service_payload(
        "AKBNK ile GARAN karşılaştır",
        known_symbols=KNOWN,
        results_by_symbol={"AKBNK": {"symbol": "AKBNK", "score": 3.9, "decision": "buy"}},
    )
    assert got["route"] == "comparison"
    assert got["ok"] is False
    assert got["error_code"] == "insufficient_comparison_results"
    assert "yeterli sembol sonucu" in got["text"]


def test_render_chat_service_text_returns_final_text() -> None:
    got = render_chat_service_text(
        "scan top 2",
        known_symbols=KNOWN,
        scan_results=[
            {"symbol": "AKBNK", "score": 4.4, "decision": "buy", "entry_missed": False},
            {"symbol": "GARAN", "score": 3.7, "decision": "watch", "entry_missed": True},
            {"symbol": "ASELS", "score": 3.1, "decision": "hold", "entry_missed": False},
        ],
    )
    assert "1) AKBNK" in got
    assert "2) GARAN" in got


def test_build_chat_service_payload_comparison_error_keeps_intent_symbols() -> None:
    got = build_chat_service_payload(
        "AKBNK ile GARAN karşılaştır",
        known_symbols=KNOWN,
        results_by_symbol={"AKBNK": {"symbol": "AKBNK", "score": 3.9, "decision": "buy"}},
    )
    assert got["route"] == "comparison"
    assert got["ok"] is False
    assert got["requested_symbols"] == ["AKBNK", "GARAN"]
    assert got["error_code"] == "insufficient_comparison_results"


def test_build_chat_service_payload_single_symbol_uses_clean_percent_format() -> None:
    got = build_chat_service_payload(
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
            }
        },
    )
    assert "+2.32%" in got["text"]
    assert "%+2.32" not in got["text"]
