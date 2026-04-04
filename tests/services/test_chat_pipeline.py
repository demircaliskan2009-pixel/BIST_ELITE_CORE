from __future__ import annotations

from bist_core.services.chat_pipeline import (
    build_chat_pipeline_result,
    render_chat_pipeline_markdown,
    render_chat_pipeline_text,
)

KNOWN = ["ASELS", "AKBNK", "GARAN", "THYAO", "TUPRS", "EREGL"]


def test_build_chat_pipeline_result_scan_contract() -> None:
    got = build_chat_pipeline_result(
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
    assert got["title"] == "Top 2 Tarama"
    assert got["leader_symbol"] == "AKBNK"
    assert got["scan_count"] == 2
    assert "1) AKBNK" in got["body"]


def test_build_chat_pipeline_result_comparison_contract() -> None:
    got = build_chat_pipeline_result(
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
    assert got["leader_symbol"] == "GARAN"
    assert got["comparison_count"] == 2
    assert "GARAN önde" in got["body"]


def test_build_chat_pipeline_result_single_symbol_contract() -> None:
    got = build_chat_pipeline_result(
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
    assert got["title"] == "ASELS Özeti"
    assert got["primary_symbol"] == "ASELS"
    assert got["requested_symbol"] == "ASELS"
    assert "giriş kaçmış" in got["body"]
    assert "+2.32%" in got["body"]


def test_build_chat_pipeline_result_market_overview_contract() -> None:
    got = build_chat_pipeline_result(
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
    assert got["leader_symbol"] == "AKBNK"
    assert got["scan_count"] == 3
    assert "Öne çıkanlar" in got["body"]


def test_build_chat_pipeline_result_error_contract() -> None:
    got = build_chat_pipeline_result(
        "AKBNK ile GARAN karşılaştır",
        known_symbols=KNOWN,
        results_by_symbol={"AKBNK": {"symbol": "AKBNK", "score": 3.9, "decision": "buy"}},
    )
    assert got["ok"] is False
    assert got["status"] == "error"
    assert got["route"] == "comparison"
    assert got["title"] == "AKBNK vs GARAN"
    assert got["error_code"] == "insufficient_comparison_results"
    assert "yeterli sembol sonucu" in got["body"]


def test_render_chat_pipeline_text_returns_body() -> None:
    got = render_chat_pipeline_text(
        "scan top 2",
        known_symbols=KNOWN,
        scan_results=[
            {"symbol": "AKBNK", "score": 4.4, "decision": "buy", "entry_missed": False},
            {"symbol": "GARAN", "score": 3.7, "decision": "watch", "entry_missed": True},
        ],
    )
    assert "1) AKBNK" in got
    assert "2) GARAN" in got


def test_render_chat_pipeline_markdown_renders_title_subtitle_body() -> None:
    got = render_chat_pipeline_markdown(
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


def test_build_chat_pipeline_result_rejects_pre_hook_on_missing_context() -> None:
    got = build_chat_pipeline_result(None)
    assert got["ok"] is False
    assert got["route"] == "hook_rejected"
    assert got["body"] == "INSUFFICIENT EVIDENCE"
    assert got["error_code"] == "hook_rejected"


def test_build_chat_pipeline_result_rejects_post_hook_template_output(monkeypatch) -> None:
    monkeypatch.setattr(
        "bist_core.services.chat_pipeline.build_chat_facade_result",
        lambda *args, **kwargs: {
            "ok": True,
            "route": "comparison",
            "title": "AKBNK vs GARAN",
            "subtitle": "2 sembol | lider=GARAN",
            "preview": "Karşılaştırma üretildi.",
            "text": "Karşılaştırma üretildi.",
            "primary_symbol": "GARAN",
            "leader_symbol": "GARAN",
            "requested_symbol": None,
            "requested_symbols": ["AKBNK", "GARAN"],
            "top_n": None,
            "scan_count": 0,
            "comparison_count": 2,
            "error_code": None,
        },
    )

    got = build_chat_pipeline_result(
        "AKBNK ile GARAN karşılaştır",
        known_symbols=KNOWN,
        results_by_symbol={
            "AKBNK": {"symbol": "AKBNK", "score": 3.9, "decision": "buy"},
            "GARAN": {"symbol": "GARAN", "score": 4.2, "decision": "buy"},
        },
    )

    assert got["ok"] is False
    assert got["route"] == "hook_rejected"
    assert got["body"] == "INSUFFICIENT EVIDENCE"


def test_build_chat_pipeline_result_fails_closed_on_facade_exception(monkeypatch) -> None:
    def _raise(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("bist_core.services.chat_pipeline.build_chat_facade_result", _raise)

    got = build_chat_pipeline_result(
        "ASELS için giriş kaçtı mı?",
        known_symbols=KNOWN,
        results_by_symbol={"ASELS": {"symbol": "ASELS", "score": 4.0, "decision": "buy"}},
    )

    assert got["ok"] is False
    assert got["route"] == "hook_rejected"
    assert got["body"] == "INSUFFICIENT EVIDENCE"


def test_build_chat_pipeline_result_routes_debug_symbol(monkeypatch) -> None:
    monkeypatch.setattr(
        "bist_core.services.chat_pipeline.dispatch_tool",
        lambda intent, payload: {
            "status": "ok",
            "intent": intent,
            "symbols": ["ASELS"],
            "data": {
                "status": "ok",
                "symbol": "ASELS",
                "day": "2025-01-31",
                "score_breakdown": {"momentum": 2.4, "liquidity": 1.1},
                "signals": {"decision": "buy"},
                "current_price_context": {
                    "current_close": 72.65,
                    "entry_status": "missed",
                    "entry_gap_pct": 2.32,
                },
            },
        },
    )

    got = build_chat_pipeline_result("why this score for ASELS", known_symbols=KNOWN)

    assert got["ok"] is True
    assert got["route"] == "debug_symbol"
    assert got["requested_symbol"] == "ASELS"
    assert got["tool_output"]["symbol"] == "ASELS"
    assert "Why this score" in got["body"]


def test_build_chat_pipeline_result_fails_closed_when_debug_tool_rejects(monkeypatch) -> None:
    monkeypatch.setattr(
        "bist_core.services.chat_pipeline.dispatch_tool",
        lambda intent, payload: {
            "status": "rejected",
            "reason": "INSUFFICIENT EVIDENCE",
            "output": "INSUFFICIENT EVIDENCE",
            "data": {},
        },
    )

    got = build_chat_pipeline_result("debug symbol ASELS", known_symbols=KNOWN)

    assert got["ok"] is False
    assert got["route"] == "hook_rejected"
    assert got["body"] == "INSUFFICIENT EVIDENCE"
