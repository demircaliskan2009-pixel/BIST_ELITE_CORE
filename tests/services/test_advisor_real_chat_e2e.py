from __future__ import annotations

import pytest

from bist_core.services import advisor as advisor_mod


def _pick_existing_symbols(candidates: list[str], day: str, limit: int = 3) -> list[str]:
    found: list[str] = []
    for symbol in candidates:
        try:
            out = advisor_mod.build_advice_for_symbol(symbol=symbol, date=day)
        except TypeError:
            try:
                out = advisor_mod.build_advice_for_symbol(symbol, day)
            except Exception:
                continue
        except Exception:
            continue
        if out is not None:
            found.append(symbol)
        if len(found) >= limit:
            break
    return found


def test_real_advisor_chat_single_symbol_e2e_contract() -> None:
    day = "2026-03-14"
    candidates = ["ASELS", "AKBNK", "GARAN", "THYAO", "TUPRS", "EREGL"]
    existing = _pick_existing_symbols(candidates, day, limit=1)
    if not existing:
        pytest.skip("No real advisor output available for candidate symbols")

    symbol = existing[0]
    got = advisor_mod.build_chat_response_for_text(
        f"{symbol} için giriş kaçtı mı?",
        day,
        known_symbols=candidates,
        scan_universe=candidates,
    )

    assert got["route"] == "single_symbol"
    assert got["primary_symbol"] == symbol
    assert isinstance(got["text"], str) and got["text"].strip()
    assert got["quality"]["route_quality_ok"] is True
    assert got["quality"]["has_core_summary"] is True


def test_real_advisor_chat_scan_e2e_contract() -> None:
    day = "2026-03-14"
    candidates = ["ASELS", "AKBNK", "GARAN", "THYAO", "TUPRS", "EREGL"]
    existing = _pick_existing_symbols(candidates, day, limit=2)
    if len(existing) < 2:
        pytest.skip("Not enough real advisor outputs available for scan contract")

    got = advisor_mod.build_chat_response_for_text(
        "scan top 2",
        day,
        known_symbols=candidates,
        scan_universe=existing,
    )

    assert got["route"] == "scan"
    assert got["ok"] is True
    assert isinstance(got["text"], str) and got["text"].strip()
    assert got["quality"]["has_ranked_list"] is True
    assert got["quality"]["route_quality_ok"] is True


def test_real_advisor_chat_market_overview_e2e_contract() -> None:
    day = "2026-03-14"
    candidates = ["ASELS", "AKBNK", "GARAN", "THYAO", "TUPRS", "EREGL"]
    existing = _pick_existing_symbols(candidates, day, limit=2)
    if len(existing) < 2:
        pytest.skip("Not enough real advisor outputs available for market overview contract")

    got = advisor_mod.build_chat_response_for_text(
        "BIST genel görünüm ne durumda?",
        day,
        known_symbols=candidates,
        scan_universe=existing,
    )

    assert got["route"] == "market_overview"
    assert got["ok"] is True
    assert isinstance(got["text"], str) and got["text"].strip()
    assert got["quality"]["route_quality_ok"] is True
