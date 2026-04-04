from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from bist_core.services.chat_dispatch import dispatch_chat_request
from bist_core.services.market_overview_brief import build_market_overview_brief


_ERROR_TEXT = {
    "insufficient_comparison_symbols": "Karşılaştırma için en az iki geçerli BIST sembolü gerekli.",
    "insufficient_comparison_results": "Karşılaştırma için yeterli sembol sonucu bulunamadı.",
    "single_symbol_resolution_failed": "Tek hisse talebi için geçerli sembol çözümlenemedi.",
    "missing_single_symbol_result": "İstenen sembol için sonuç bulunamadı.",
    "empty_scan_results": "Taranacak geçerli aday bulunamadı.",
    "unknown_route": "Mesaj yönlendirilemedi.",
    "missing_market_overview_text": "Piyasa özeti için metin veya tarama verisi gerekli.",
}


def _coerce_market_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def build_chat_response(
    text: str | None,
    *,
    known_symbols: Sequence[str] | None = None,
    results_by_symbol: Mapping[str, Mapping[str, Any] | dict[str, Any]] | None = None,
    scan_results: Sequence[Mapping[str, Any] | dict[str, Any]] | None = None,
    market_overview_text: str | None = None,
    default_scan_n: int = 5,
) -> dict[str, Any]:
    dispatched = dispatch_chat_request(
        text,
        known_symbols=known_symbols,
        results_by_symbol=results_by_symbol,
        scan_results=scan_results,
        default_scan_n=default_scan_n,
    )

    route = dispatched.get("route") or "unknown"
    ok = bool(dispatched.get("ok"))
    error_code = dispatched.get("error_code")
    response_text = str(dispatched.get("text") or "").strip()

    if route == "market_overview":
        market_text = _coerce_market_text(market_overview_text)
        if not market_text:
            market_text = build_market_overview_brief(scan_results or [], top_n=min(max(default_scan_n, 1), 5))
        if market_text:
            response_text = market_text
            ok = True
            error_code = None
        elif not response_text:
            ok = False
            error_code = "missing_market_overview_text"

    if not response_text and error_code:
        response_text = _ERROR_TEXT.get(error_code, "İstek işlenemedi.")

    if not response_text and ok and route == "single_symbol":
        payload = dispatched.get("payload") or {}
        symbol = payload.get("symbol") if isinstance(payload, Mapping) else None
        if symbol:
            response_text = f"{symbol} için özet üretildi."
    elif not response_text and ok and route == "comparison":
        response_text = "Karşılaştırma üretildi."
    elif not response_text and ok and route == "scan":
        response_text = "Tarama sonucu üretildi."

    return {
        **dispatched,
        "ok": bool(ok),
        "error_code": error_code,
        "text": response_text.strip(),
        "route": route,
    }
