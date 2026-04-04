from __future__ import annotations

from dataclasses import dataclass

from bist_core.services import advisor as advisor_mod


KNOWN = ["ASELS", "AKBNK", "GARAN", "THYAO", "TUPRS", "EREGL"]


@dataclass
class AdviceStub:
    symbol: str
    date: str
    decision: str
    score: float
    entry: float
    stop: float
    target: float
    rationale: str


def test_public_entrypoint_surfaces_fail_closed_live_context_metadata_for_dataclass_advice() -> None:
    original = advisor_mod.build_advice_for_symbol

    def fake_build_advice_for_symbol(symbol, date, root=None):
        obj = AdviceStub(
            symbol=symbol,
            date="2025-12-16",
            decision="buy",
            score=1.48,
            entry=43.98,
            stop=42.68,
            target=44.86,
            rationale="Momentum pozitif",
        )
        obj.live_payload = {
            "current_price": 330.0,
            "last_price": 330.0,
            "price": 330.0,
        }
        return obj

    advisor_mod.build_advice_for_symbol = fake_build_advice_for_symbol
    try:
        got = advisor_mod.build_chat_response_for_text(
            "ASELS için giriş kaçtı mı?",
            "2026-03-14",
            known_symbols=KNOWN,
            scan_universe=["ASELS", "AKBNK", "GARAN"],
        )
    finally:
        advisor_mod.build_advice_for_symbol = original

    assert got["ok"] is True
    assert got["route"] == "single_symbol"
    assert got["live_context_meta"]["suppressed"] is True
    assert got["live_context_meta"]["suppression_reason"] == "live_price_out_of_band"
    assert got["live_context_meta"]["suppressed_symbols"] == ["ASELS"]
    assert got["quality"]["has_live_context_suppressed"] is True
    assert got["quality"]["live_context_suppression_reason"] == "live_price_out_of_band"
    assert "330.0" not in got["text"]
    assert "Canlı veri ölçek tutarsızlığı nedeniyle canlı bağlam gizlendi." in got["text"]


def test_public_entrypoint_keeps_sane_live_context_metadata_for_dataclass_advice() -> None:
    original = advisor_mod.build_advice_for_symbol

    def fake_build_advice_for_symbol(symbol, date, root=None):
        obj = AdviceStub(
            symbol=symbol,
            date="2025-12-16",
            decision="buy",
            score=4.0,
            entry=71.0,
            stop=69.5,
            target=76.0,
            rationale="Momentum güçlü",
        )
        obj.live_payload = {
            "current_price": 72.6500015258789,
            "last_price": 72.65,
            "price": 72.65,
        }
        return obj

    advisor_mod.build_advice_for_symbol = fake_build_advice_for_symbol
    try:
        got = advisor_mod.build_chat_response_for_text(
            "ASELS için giriş kaçtı mı?",
            "2026-03-14",
            known_symbols=KNOWN,
            scan_universe=["ASELS", "AKBNK", "GARAN"],
        )
    finally:
        advisor_mod.build_advice_for_symbol = original

    assert got["ok"] is True
    assert got["route"] == "single_symbol"
    assert got["live_context_meta"]["suppressed"] is False
    assert got["live_context_meta"]["suppression_reason"] == ""
    assert got["quality"]["has_live_context_suppressed"] is False
    assert got["quality"]["live_context_suppression_reason"] == ""
    assert "+2.32%" in got["text"]
    assert "Canlı fiyat girişin +2.32% üzerinde" in got["text"]
