from __future__ import annotations

from bist_core.services.chat_application_service import (
    build_chat_application_service_result,
    normalize_chat_application_request,
    render_chat_application_markdown,
    render_chat_application_text,
)


KNOWN = ["ASELS", "AKBNK", "GARAN", "THYAO", "TUPRS", "EREGL"]


def test_normalize_chat_application_request_coerces_fields() -> None:
    got = normalize_chat_application_request(
        {
            "query": "scan top 2",
            "known_symbols": "ASELS AKBNK GARAN",
            "symbol_results": {"ASELS": {"symbol": "ASELS", "score": 4.0}},
            "ranked_candidates": [{"symbol": "AKBNK", "score": 4.4}],
            "default_scan_n": "3",
        }
    )
    assert got["text"] == "scan top 2"
    assert got["known_symbols"] == ["ASELS", "AKBNK", "GARAN"]
    assert list(got["results_by_symbol"].keys()) == ["ASELS"]
    assert got["scan_results"][0]["symbol"] == "AKBNK"
    assert got["default_scan_n"] == 3


def test_build_chat_application_service_result_scan_contract() -> None:
    got = build_chat_application_service_result(
        text="scan top 2",
        known_symbols=KNOWN,
        scan_results=[
            {"symbol": "AKBNK", "score": 4.4, "decision": "buy", "entry_missed": False},
            {"symbol": "GARAN", "score": 3.7, "decision": "watch", "entry_missed": True},
            {"symbol": "ASELS", "score": 3.1, "decision": "hold", "entry_missed": False},
        ],
    )
    assert got["ok"] is True
    assert got["route"] == "scan"
    assert got["leader_symbol"] == "AKBNK"
    assert got["response"]["metrics"]["scan_count"] == 2
    assert "1) AKBNK" in got["text"]


def test_build_chat_application_service_result_comparison_contract() -> None:
    got = build_chat_application_service_result(
        {
            "text": "AKBNK ile GARAN karşılaştır",
            "known_symbols": KNOWN,
            "results_by_symbol": {
                "AKBNK": {"symbol": "AKBNK", "score": 3.9, "decision": "buy"},
                "GARAN": {"symbol": "GARAN", "score": 4.2, "decision": "buy"},
                "ASELS": {"symbol": "ASELS", "score": 9.9, "decision": "buy"},
            },
        }
    )
    assert got["ok"] is True
    assert got["route"] == "comparison"
    assert got["leader_symbol"] == "GARAN"
    assert got["response"]["title"] == "AKBNK vs GARAN"
    assert "GARAN önde" in got["text"]


def test_build_chat_application_service_result_single_symbol_contract() -> None:
    got = build_chat_application_service_result(
        {
            "message": "ASELS için giriş kaçtı mı?",
            "known_symbols": KNOWN,
            "results_by_symbol": {
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
        }
    )
    assert got["ok"] is True
    assert got["route"] == "single_symbol"
    assert got["primary_symbol"] == "ASELS"
    assert got["response"]["symbols"]["requested_symbol"] == "ASELS"
    assert "+2.32%" in got["text"]


def test_build_chat_application_service_result_market_overview_contract() -> None:
    got = build_chat_application_service_result(
        text="BIST genel görünüm ne durumda?",
        known_symbols=KNOWN,
        scan_results=[
            {"symbol": "AKBNK", "score": 4.4, "decision": "buy", "entry_missed": False},
            {"symbol": "GARAN", "score": 3.7, "decision": "watch", "entry_missed": True},
            {"symbol": "ASELS", "score": 3.1, "decision": "hold", "entry_missed": False},
        ],
    )
    assert got["ok"] is True
    assert got["route"] == "market_overview"
    assert got["leader_symbol"] == "AKBNK"
    assert got["response"]["metrics"]["scan_count"] == 3
    assert "Öne çıkanlar" in got["text"]


def test_build_chat_application_service_result_error_contract() -> None:
    got = build_chat_application_service_result(
        text="AKBNK ile GARAN karşılaştır",
        known_symbols=KNOWN,
        results_by_symbol={"AKBNK": {"symbol": "AKBNK", "score": 3.9, "decision": "buy"}},
    )
    assert got["ok"] is False
    assert got["route"] == "comparison"
    assert got["error"]["code"] == "insufficient_comparison_results"
    assert "yeterli sembol sonucu" in got["text"]


def test_render_chat_application_text_returns_text() -> None:
    got = render_chat_application_text(
        text="scan top 2",
        known_symbols=KNOWN,
        scan_results=[
            {"symbol": "AKBNK", "score": 4.4, "decision": "buy", "entry_missed": False},
            {"symbol": "GARAN", "score": 3.7, "decision": "watch", "entry_missed": True},
        ],
    )
    assert "1) AKBNK" in got
    assert "2) GARAN" in got


def test_render_chat_application_markdown_returns_markdown() -> None:
    got = render_chat_application_markdown(
        text="scan top 2",
        known_symbols=KNOWN,
        scan_results=[
            {"symbol": "AKBNK", "score": 4.4, "decision": "buy", "entry_missed": False},
            {"symbol": "GARAN", "score": 3.7, "decision": "watch", "entry_missed": True},
        ],
    )
    assert "## Top 2 Tarama" in got
    assert "2 aday | lider=AKBNK" in got
    assert "1) AKBNK" in got
