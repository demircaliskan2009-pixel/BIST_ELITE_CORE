from __future__ import annotations

from dataclasses import dataclass

from bist_core.services.advisor_chat_adapter import (
    build_chat_result_from_advice_map,
    build_results_by_symbol_from_advice_map,
    build_scan_results_from_advice_map,
    normalize_advice_like_result,
)


@dataclass
class DummyAdvice:
    symbol: str
    decision: str
    score: float
    entry: float | None = None
    stop: float | None = None
    target: float | None = None
    rationale: str | None = None
    live_payload: dict | None = None


KNOWN = ["ASELS", "AKBNK", "GARAN", "THYAO", "TUPRS", "EREGL"]


def test_normalize_advice_like_result_from_dataclass() -> None:
    advice = DummyAdvice(
        symbol="ASELS",
        decision="buy",
        score=4.0,
        entry=71.0,
        stop=69.5,
        target=76.0,
        rationale="Momentum güçlü",
        live_payload={"current_price": 72.6500015258789, "last_price": 72.65, "price": 72.65},
    )
    got = normalize_advice_like_result(advice)
    assert got["symbol"] == "ASELS"
    assert got["decision"] == "buy"
    assert got["score"] == 4.0
    assert got["entry"] == 71.0
    assert got["stop"] == 69.5
    assert got["target"] == 76.0
    assert got["rationale"] == "Momentum güçlü"
    assert got["live_payload"]["price"] == 72.65


def test_build_results_by_symbol_from_advice_map_preserves_symbols() -> None:
    advice_map = {
        "ASELS": DummyAdvice(symbol="ASELS", decision="buy", score=4.0),
        "AKBNK": {"symbol": "AKBNK", "decision": "watch", "score": 3.2},
    }
    got = build_results_by_symbol_from_advice_map(advice_map)
    assert list(got.keys()) == ["ASELS", "AKBNK"]
    assert got["ASELS"]["symbol"] == "ASELS"
    assert got["AKBNK"]["decision"] == "watch"


def test_build_scan_results_from_advice_map_returns_list() -> None:
    advice_map = {
        "AKBNK": {"symbol": "AKBNK", "decision": "buy", "score": 4.4},
        "GARAN": {"symbol": "GARAN", "decision": "watch", "score": 3.7},
    }
    got = build_scan_results_from_advice_map(advice_map)
    assert len(got) == 2
    assert got[0]["symbol"] == "AKBNK"
    assert got[1]["symbol"] == "GARAN"


def test_build_chat_result_from_advice_map_single_symbol_contract() -> None:
    advice_map = {
        "ASELS": DummyAdvice(
            symbol="ASELS",
            decision="buy",
            score=4.0,
            entry=71.0,
            stop=69.5,
            target=76.0,
            rationale="Momentum güçlü",
            live_payload={"current_price": 72.6500015258789, "last_price": 72.65, "price": 72.65},
        )
    }
    got = build_chat_result_from_advice_map(
        "ASELS için giriş kaçtı mı?",
        advice_map=advice_map,
        known_symbols=KNOWN,
    )
    assert got["ok"] is True
    assert got["route"] == "single_symbol"
    assert got["primary_symbol"] == "ASELS"
    assert "+2.32%" in got["text"]
    assert "giriş kaçmış" in got["text"]


def test_build_chat_result_from_advice_map_comparison_contract() -> None:
    advice_map = {
        "AKBNK": {"symbol": "AKBNK", "decision": "buy", "score": 3.9},
        "GARAN": {"symbol": "GARAN", "decision": "buy", "score": 4.2},
        "ASELS": {"symbol": "ASELS", "decision": "buy", "score": 9.9},
    }
    got = build_chat_result_from_advice_map(
        "AKBNK ile GARAN karşılaştır",
        advice_map=advice_map,
        known_symbols=KNOWN,
    )
    assert got["ok"] is True
    assert got["route"] == "comparison"
    assert got["leader_symbol"] == "GARAN"
    assert "GARAN önde" in got["text"]


def test_build_chat_result_from_advice_map_scan_contract() -> None:
    advice_map = {
        "AKBNK": {"symbol": "AKBNK", "decision": "buy", "score": 4.4},
        "GARAN": {"symbol": "GARAN", "decision": "watch", "score": 3.7, "entry_missed": True},
        "ASELS": {"symbol": "ASELS", "decision": "hold", "score": 3.1},
    }
    got = build_chat_result_from_advice_map(
        "scan top 2",
        advice_map=advice_map,
        known_symbols=KNOWN,
    )
    assert got["ok"] is True
    assert got["route"] == "scan"
    assert got["leader_symbol"] == "AKBNK"
    assert "1) AKBNK" in got["text"]
    assert "2) GARAN" in got["text"]


def test_build_chat_result_from_advice_map_market_overview_contract() -> None:
    advice_map = {
        "AKBNK": {"symbol": "AKBNK", "decision": "buy", "score": 4.4},
        "GARAN": {"symbol": "GARAN", "decision": "watch", "score": 3.7, "entry_missed": True},
        "ASELS": {"symbol": "ASELS", "decision": "hold", "score": 3.1},
    }
    got = build_chat_result_from_advice_map(
        "BIST genel görünüm ne durumda?",
        advice_map=advice_map,
        known_symbols=KNOWN,
    )
    assert got["ok"] is True
    assert got["route"] == "market_overview"
    assert got["leader_symbol"] == "AKBNK"
    assert "Öne çıkanlar" in got["text"]
