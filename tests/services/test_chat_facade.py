from __future__ import annotations

from bist_core.services.chat_facade import (
    build_chat_facade_result,
    render_chat_facade_text,
)


KNOWN = ["ASELS", "AKBNK", "GARAN", "THYAO", "TUPRS", "EREGL"]


def test_build_chat_facade_result_scan_sets_title_subtitle_and_preview() -> None:
    got = build_chat_facade_result(
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
    assert got["title"] == "Top 2 Tarama"
    assert got["subtitle"] == "2 aday | lider=AKBNK"
    assert got["leader_symbol"] == "AKBNK"
    assert got["preview"].startswith("AKBNK lider")


def test_build_chat_facade_result_comparison_sets_vs_title() -> None:
    got = build_chat_facade_result(
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
    assert got["title"] == "AKBNK vs GARAN"
    assert got["subtitle"] == "2 sembol | lider=GARAN"
    assert got["leader_symbol"] == "GARAN"
    assert "GARAN önde" in got["text"]


def test_build_chat_facade_result_single_symbol_sets_symbol_title() -> None:
    got = build_chat_facade_result(
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
    assert got["title"] == "ASELS Özeti"
    assert got["subtitle"] == "Canlı giriş özeti | sembol=ASELS"
    assert got["primary_symbol"] == "ASELS"
    assert "giriş kaçmış" in got["text"]


def test_build_chat_facade_result_market_overview_sets_default_title() -> None:
    got = build_chat_facade_result(
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
    assert got["title"] == "Piyasa Özeti"
    assert got["subtitle"] == "3 öne çıkan aday | lider=AKBNK"
    assert "Öne çıkanlar" in got["text"]


def test_build_chat_facade_result_error_keeps_human_text() -> None:
    got = build_chat_facade_result(
        "AKBNK ile GARAN karşılaştır",
        known_symbols=KNOWN,
        results_by_symbol={"AKBNK": {"symbol": "AKBNK", "score": 3.9, "decision": "buy"}},
    )
    assert got["route"] == "comparison"
    assert got["ok"] is False
    assert got["title"] == "AKBNK vs GARAN"
    assert got["error_code"] == "insufficient_comparison_results"
    assert "yeterli sembol sonucu" in got["text"]


def test_render_chat_facade_text_returns_final_text() -> None:
    got = render_chat_facade_text(
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
