from __future__ import annotations

from bist_core.services.advisor_chat_adapter import build_chat_result_from_advice_map
from bist_core.services.live_price_sanity import sanitize_live_payload_for_chat


KNOWN = ["ASELS", "AKBNK", "GARAN", "THYAO", "TUPRS", "EREGL"]


def test_sanitize_live_payload_for_chat_drops_outlier_scale() -> None:
    got = sanitize_live_payload_for_chat(
        {
            "symbol": "ASELS",
            "decision": "buy",
            "score": 1.48,
            "entry": 43.98,
            "stop": 42.68,
            "target": 44.86,
            "rationale": "Momentum pozitif",
            "live_payload": {
                "current_price": 330.0,
                "last_price": 330.0,
                "price": 330.0,
            },
        }
    )
    assert "live_payload" not in got
    assert got["live_price_sanity"]["ok"] is False
    assert got["live_price_sanity"]["reason"] == "live_price_out_of_band"
    assert got["live_price_sanity"]["ratio"] > 2.5


def test_sanitize_live_payload_for_chat_keeps_normal_scale() -> None:
    got = sanitize_live_payload_for_chat(
        {
            "symbol": "ASELS",
            "decision": "buy",
            "score": 4.0,
            "entry": 71.0,
            "stop": 69.5,
            "target": 76.0,
            "rationale": "Momentum güçlü",
            "live_payload": {
                "current_price": 72.65,
                "last_price": 72.65,
                "price": 72.65,
            },
        }
    )
    assert got["live_payload"]["price"] == 72.65
    assert got["live_price_sanity"]["ok"] is True


def test_build_chat_result_from_advice_map_suppresses_bad_live_context_gap() -> None:
    got = build_chat_result_from_advice_map(
        "ASELS için giriş kaçtı mı?",
        advice_map={
            "ASELS": {
                "symbol": "ASELS",
                "decision": "buy",
                "score": 1.48,
                "entry": 43.98,
                "stop": 42.68,
                "target": 44.86,
                "rationale": "Momentum pozitif",
                "live_payload": {
                    "current_price": 330.0,
                    "last_price": 330.0,
                    "price": 330.0,
                },
            }
        },
        known_symbols=KNOWN,
    )
    assert got["ok"] is True
    assert got["route"] == "single_symbol"
    assert got["primary_symbol"] == "ASELS"
    assert "330.0" not in got["text"]
    assert "+650" not in got["text"]
    assert "Canlı fiyat" not in got["text"]
    assert "43.98" in got["text"]


def test_build_chat_result_from_advice_map_keeps_live_context_when_sane() -> None:
    got = build_chat_result_from_advice_map(
        "ASELS için giriş kaçtı mı?",
        advice_map={
            "ASELS": {
                "symbol": "ASELS",
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
        },
        known_symbols=KNOWN,
    )
    assert got["ok"] is True
    assert got["route"] == "single_symbol"
    assert "+2.32%" in got["text"]
    assert "Canlı fiyat" in got["text"]
