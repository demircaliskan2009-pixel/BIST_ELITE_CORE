from __future__ import annotations

from bist_core.services.chat_endpoint_payload import (
    build_chat_endpoint_payload,
    render_chat_endpoint_markdown,
    render_chat_endpoint_text,
)


KNOWN = ["ASELS", "AKBNK", "GARAN", "THYAO", "TUPRS", "EREGL"]


def test_build_chat_endpoint_payload_scan_contract() -> None:
    got = build_chat_endpoint_payload(
        "scan top 2",
        known_symbols=KNOWN,
        scan_results=[
            {"symbol": "AKBNK", "score": 4.4, "decision": "buy", "entry_missed": False},
            {"symbol": "GARAN", "score": 3.7, "decision": "watch", "entry_missed": True},
            {"symbol": "ASELS", "score": 3.1, "decision": "hold", "entry_missed": False},
        ],
    )
    assert got["ok"] is True
    assert got["status"] == "ok"
    assert got["route"] == "scan"
    assert got["symbols"]["leader"] == "AKBNK"
    assert got["metrics"]["scan_count"] == 2
    assert got["cards"][0]["title"] == "Top 2 Tarama"
    assert "1) AKBNK" in got["text"]


def test_build_chat_endpoint_payload_comparison_contract() -> None:
    got = build_chat_endpoint_payload(
        "AKBNK ile GARAN karşılaştır",
        known_symbols=KNOWN,
        results_by_symbol={
            "AKBNK": {"symbol": "AKBNK", "score": 3.9, "decision": "buy"},
            "GARAN": {"symbol": "GARAN", "score": 4.2, "decision": "buy"},
            "ASELS": {"symbol": "ASELS", "score": 9.9, "decision": "buy"},
        },
    )
    assert got["ok"] is True
    assert got["route"] == "comparison"
    assert got["title"] == "AKBNK vs GARAN"
    assert got["symbols"]["leader"] == "GARAN"
    assert got["metrics"]["comparison_count"] == 2
    assert "GARAN önde" in got["text"]


def test_build_chat_endpoint_payload_single_symbol_contract() -> None:
    got = build_chat_endpoint_payload(
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
    assert got["ok"] is True
    assert got["route"] == "single_symbol"
    assert got["symbols"]["requested_symbol"] == "ASELS"
    assert got["symbols"]["primary"] == "ASELS"
    assert got["cards"][0]["title"] == "ASELS Özeti"
    assert "giriş kaçmış" in got["text"]
    assert "+2.32%" in got["text"]


def test_build_chat_endpoint_payload_market_overview_contract() -> None:
    got = build_chat_endpoint_payload(
        "BIST genel görünüm ne durumda?",
        known_symbols=KNOWN,
        scan_results=[
            {"symbol": "AKBNK", "score": 4.4, "decision": "buy", "entry_missed": False},
            {"symbol": "GARAN", "score": 3.7, "decision": "watch", "entry_missed": True},
            {"symbol": "ASELS", "score": 3.1, "decision": "hold", "entry_missed": False},
        ],
    )
    assert got["ok"] is True
    assert got["route"] == "market_overview"
    assert got["title"] == "Piyasa Özeti"
    assert got["symbols"]["leader"] == "AKBNK"
    assert got["metrics"]["scan_count"] == 3
    assert "Öne çıkanlar" in got["text"]


def test_build_chat_endpoint_payload_error_contract() -> None:
    got = build_chat_endpoint_payload(
        "AKBNK ile GARAN karşılaştır",
        known_symbols=KNOWN,
        results_by_symbol={"AKBNK": {"symbol": "AKBNK", "score": 3.9, "decision": "buy"}},
    )
    assert got["ok"] is False
    assert got["status"] == "error"
    assert got["route"] == "comparison"
    assert got["title"] == "AKBNK vs GARAN"
    assert got["error"]["code"] == "insufficient_comparison_results"
    assert "yeterli sembol sonucu" in got["error"]["message"]


def test_render_chat_endpoint_text_returns_text() -> None:
    got = render_chat_endpoint_text(
        "scan top 2",
        known_symbols=KNOWN,
        scan_results=[
            {"symbol": "AKBNK", "score": 4.4, "decision": "buy", "entry_missed": False},
            {"symbol": "GARAN", "score": 3.7, "decision": "watch", "entry_missed": True},
        ],
    )
    assert "1) AKBNK" in got
    assert "2) GARAN" in got


def test_render_chat_endpoint_markdown_returns_card_like_markdown() -> None:
    got = render_chat_endpoint_markdown(
        "scan top 2",
        known_symbols=KNOWN,
        scan_results=[
            {"symbol": "AKBNK", "score": 4.4, "decision": "buy", "entry_missed": False},
            {"symbol": "GARAN", "score": 3.7, "decision": "watch", "entry_missed": True},
        ],
    )
    assert "## Top 2 Tarama" in got
    assert "2 aday | lider=AKBNK" in got
    assert "1) AKBNK" in got
