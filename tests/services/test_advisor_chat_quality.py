from __future__ import annotations

from bist_core.services import advisor as advisor_mod
from bist_core.services.advisor_chat_service import build_advisor_chat_service_result
from bist_core.services.advisor_chat_quality import build_advisor_chat_quality_metrics


KNOWN = ["ASELS", "AKBNK", "GARAN", "THYAO", "TUPRS", "EREGL"]


def test_build_advisor_chat_quality_metrics_scan_route() -> None:
    got = build_advisor_chat_quality_metrics(
        {
            "route": "scan",
            "text": "AKBNK lider; skor farkı +0.70. karar=buy.\nSıralama:\n1) AKBNK | score=4.40 | karar=buy\n2) GARAN | score=3.70 | karar=watch | giriş kaçmış",
            "title": "Top 2 Tarama",
            "subtitle": "2 aday | lider=AKBNK",
            "leader_symbol": "AKBNK",
            "advisor_count": 2,
            "response": {"metrics": {"top_n": 2}, "symbols": {"requested": ["AKBNK", "GARAN"], "primary": "AKBNK", "leader": "AKBNK"}},
        }
    )
    assert got["route_quality_ok"] is True
    assert got["has_ranked_list"] is True
    assert got["ranked_line_count"] == 2
    assert got["leader_symbol"] == "AKBNK"


def test_build_advisor_chat_service_result_single_symbol_quality_contract() -> None:
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
            text="ASELS için giriş kaçtı mı?",
            day="2026-03-14",
            known_symbols=KNOWN,
            scan_universe=["AKBNK", "GARAN", "ASELS"],
        )
    finally:
        advisor_mod.build_advice_for_symbol = original

    q = got["quality"]
    assert got["ok"] is True
    assert got["route"] == "single_symbol"
    assert q["route_quality_ok"] is True
    assert q["has_live_context"] is True
    assert q["has_levels"] is True
    assert q["has_reasoning"] is True
    assert "+2.32%" in got["text"]


def test_build_advisor_chat_service_result_comparison_quality_contract() -> None:
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
            text="AKBNK ile GARAN karşılaştır",
            day="2026-03-14",
            known_symbols=KNOWN,
            scan_universe=["AKBNK", "GARAN", "ASELS"],
        )
    finally:
        advisor_mod.build_advice_for_symbol = original

    q = got["quality"]
    assert got["ok"] is True
    assert got["route"] == "comparison"
    assert q["route_quality_ok"] is True
    assert q["has_ranked_list"] is True
    assert q["mentions_leader"] is True
    assert q["ranked_line_count"] == 2
    assert "GARAN önde" in got["text"]


def test_build_advisor_chat_service_result_market_overview_quality_contract() -> None:
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
            text="BIST genel görünüm ne durumda?",
            day="2026-03-14",
            known_symbols=KNOWN,
            scan_universe=["AKBNK", "GARAN", "ASELS"],
        )
    finally:
        advisor_mod.build_advice_for_symbol = original

    q = got["quality"]
    assert got["ok"] is True
    assert got["route"] == "market_overview"
    assert q["route_quality_ok"] is True
    assert q["has_market_breadth"] is True
    assert q["leader_symbol"] == "AKBNK"
    assert "Öne çıkanlar" in got["text"]


def test_build_advisor_chat_service_result_partial_failure_keeps_quality_gate_green() -> None:
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
        got = build_advisor_chat_service_result(
            text="scan top 2",
            day="2026-03-14",
            known_symbols=KNOWN,
            scan_universe=["AKBNK", "GARAN", "ASELS"],
        )
    finally:
        advisor_mod.build_advice_for_symbol = original

    q = got["quality"]
    assert got["ok"] is True
    assert got["route"] == "scan"
    assert got["advisor_errors"] == {"GARAN": "RuntimeError"}
    assert got["advisor_error_count"] == 1
    assert q["has_error_map"] is True
    assert q["route_quality_ok"] is True
    assert "1) AKBNK" in got["text"]
    assert "2) ASELS" in got["text"]


def test_build_advisor_chat_quality_metrics_reads_nested_endpoint_payload() -> None:
    got = build_advisor_chat_quality_metrics(
        {
            "route": "comparison",
            "text": "GARAN önde; skor farkı +0.30. karar=buy.\nSıralama:\n1) GARAN | score=4.20 | karar=buy\n2) AKBNK | score=3.90 | karar=buy",
            "primary_symbol": "GARAN",
            "leader_symbol": "GARAN",
            "response": {
                "route": "comparison",
                "response": {
                    "symbols": {
                        "requested": ["AKBNK", "GARAN"],
                        "requested_symbol": None,
                        "primary": "GARAN",
                        "leader": "GARAN",
                    },
                    "metrics": {
                        "top_n": None,
                        "scan_count": 0,
                        "comparison_count": 2,
                    },
                },
            },
        }
    )
    assert got["requested_symbols"] == ["AKBNK", "GARAN"]
    assert got["primary_symbol"] == "GARAN"
    assert got["leader_symbol"] == "GARAN"
    assert got["route_quality_ok"] is True


def test_build_advisor_chat_quality_metrics_single_symbol_minimal_real_output_contract() -> None:
    got = build_advisor_chat_quality_metrics(
        {
            "route": "single_symbol",
            "text": "ASELS | karar=watch | score=2.50.",
            "title": "ASELS Özeti",
            "subtitle": "Tek Hisse Özeti",
            "primary_symbol": "ASELS",
            "response": {
                "response": {
                    "symbols": {
                        "requested": ["ASELS"],
                        "requested_symbol": "ASELS",
                        "primary": "ASELS",
                        "leader": None,
                    },
                    "metrics": {
                        "top_n": None,
                        "scan_count": 0,
                        "comparison_count": 0,
                    },
                }
            },
        }
    )
    assert got["has_core_summary"] is True
    assert got["route_quality_ok"] is True
