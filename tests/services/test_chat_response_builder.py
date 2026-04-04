from __future__ import annotations

from bist_core.services.chat_response_builder import build_chat_response


KNOWN = ["ASELS", "AKBNK", "GARAN", "THYAO", "TUPRS", "EREGL"]


def test_build_chat_response_scan_returns_ranked_text() -> None:
    got = build_chat_response(
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
    assert "1) AKBNK" in got["text"]
    assert "2) GARAN" in got["text"]


def test_build_chat_response_comparison_returns_comparison_text() -> None:
    got = build_chat_response(
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
    assert "GARAN önde" in got["text"]


def test_build_chat_response_single_symbol_returns_live_aware_brief() -> None:
    got = build_chat_response(
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
    assert "ASELS" in got["text"]
    assert "giriş kaçmış" in got["text"]
    assert "hedef=76.00" in got["text"]


def test_build_chat_response_market_overview_uses_supplied_text() -> None:
    got = build_chat_response(
        "BIST genel görünüm ne durumda?",
        known_symbols=KNOWN,
        market_overview_text="BIST genel görünüm nötr-pozitif, banka tarafı görece güçlü.",
    )
    assert got["route"] == "market_overview"
    assert got["ok"] is True
    assert "nötr-pozitif" in got["text"]


def test_build_chat_response_market_overview_falls_back_to_scan_summary() -> None:
    got = build_chat_response(
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
    assert "AKBNK" in got["text"]
    assert "Öne çıkanlar" in got["text"]


def test_build_chat_response_comparison_error_is_human_readable() -> None:
    got = build_chat_response(
        "AKBNK ile GARAN karşılaştır",
        known_symbols=KNOWN,
        results_by_symbol={"AKBNK": {"symbol": "AKBNK", "score": 3.9, "decision": "buy"}},
    )
    assert got["route"] == "comparison"
    assert got["ok"] is False
    assert got["error_code"] == "insufficient_comparison_results"
    assert "yeterli sembol sonucu" in got["text"]


def test_build_chat_response_market_overview_requires_text_or_scan_results() -> None:
    got = build_chat_response("BIST genel görünüm ne durumda?", known_symbols=KNOWN)
    assert got["route"] == "market_overview"
    assert got["ok"] is False
    assert got["error_code"] == "missing_market_overview_text"
