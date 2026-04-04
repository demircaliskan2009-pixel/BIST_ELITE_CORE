from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any


_SYMBOL_RE = re.compile(r"(?<![A-ZÇĞİÖŞÜ0-9])[$#]?([A-ZÇĞİÖŞÜ]{4,6})(?![A-ZÇĞİÖŞÜ0-9])")
_TOP_N_PATTERNS = (
    re.compile(r"\btop\s*(\d{1,2})\b", re.IGNORECASE),
    re.compile(r"\bscan\s+top\s*(\d{1,2})\b", re.IGNORECASE),
    re.compile(r"\bilk\s+(\d{1,2})\b", re.IGNORECASE),
    re.compile(r"\ben\s+iyi\s+(\d{1,2})\b", re.IGNORECASE),
    re.compile(r"\b(\d{1,2})\s*adet\b", re.IGNORECASE),
)

_IGNORE_TOKENS = {
    "BIST", "BIST100", "XU100", "XU030", "KAP", "VIOP", "TRY", "TL", "USD",
    "EUR", "TOP", "SCAN", "LONG", "SHORT", "STOP", "HEDEF", "AL", "SAT",
    "HOLD", "WAIT", "ROBOT", "CORE", "TEST", "LIVE", "EOD",
}

_COMPARISON_HINTS = (
    "karşılaştır", "karsilastir", "kıyasla", "kiyasla", "vs", "versus", "ile karşılaştır",
    "ile karsilastir", "mi yoksa", "mu yoksa", "mı yoksa", "mü yoksa", "hangisi"
)

_SCAN_HINTS = (
    "scan", "tara", "listele", "top ", "ilk ", "en iyi ", "fırsat", "firsat"
)

_MARKET_HINTS = (
    "bist", "piyasa", "endeks", "sektör", "sektor", "hacim", "genel görünüm", "genel gorunum"
)


def _normalize_text(text: str | None) -> str:
    return (text or "").strip()


def _upper_text(text: str) -> str:
    return text.upper().replace("İ", "I")


def _known_symbol_set(known_symbols: Iterable[str] | None) -> set[str] | None:
    if known_symbols is None:
        return None
    out = {str(x).upper().strip() for x in known_symbols if str(x).strip()}
    return out or None


def extract_bist_symbols(
    text: str | None,
    known_symbols: Iterable[str] | None = None,
    *,
    max_symbols: int = 8,
) -> list[str]:
    raw = _normalize_text(text)
    if not raw:
        return []

    known = _known_symbol_set(known_symbols)
    upper_text = _upper_text(raw)
    out: list[str] = []

    for match in _SYMBOL_RE.finditer(upper_text):
        token = match.group(1).upper().strip()
        if token in _IGNORE_TOKENS:
            continue
        if known is not None and token not in known:
            continue
        if token not in out:
            out.append(token)
        if len(out) >= max_symbols:
            break

    return out


def detect_top_n(text: str | None) -> int | None:
    raw = _normalize_text(text)
    if not raw:
        return None

    for pattern in _TOP_N_PATTERNS:
        m = pattern.search(raw)
        if not m:
            continue
        try:
            value = int(m.group(1))
        except (TypeError, ValueError):
            continue
        if 1 <= value <= 50:
            return value
    return None


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    lowered = text.casefold()
    return any(needle.casefold() in lowered for needle in needles)


def classify_chat_intent(
    text: str | None,
    known_symbols: Iterable[str] | None = None,
) -> dict[str, Any]:
    raw = _normalize_text(text)
    symbols = extract_bist_symbols(raw, known_symbols=known_symbols)
    top_n = detect_top_n(raw)

    wants_comparison = len(symbols) >= 2 and _contains_any(raw, _COMPARISON_HINTS)
    if not wants_comparison and len(symbols) >= 2:
        wants_comparison = any(sep in raw.casefold() for sep in (" vs ", "/", " ile ", " ya da ", " yoksa "))

    wants_scan = top_n is not None or _contains_any(raw, _SCAN_HINTS)
    wants_market = _contains_any(raw, _MARKET_HINTS)

    if wants_comparison and len(symbols) >= 2:
        intent = "comparison"
    elif wants_scan and top_n is not None:
        intent = "scan"
    elif len(symbols) == 1:
        intent = "single_symbol"
    elif wants_market:
        intent = "market_overview"
    else:
        intent = "unknown"

    return {
        "intent": intent,
        "symbols": symbols,
        "symbol_count": len(symbols),
        "top_n": top_n,
        "wants_scan": bool(wants_scan),
        "wants_comparison": bool(wants_comparison),
        "wants_single_symbol": len(symbols) == 1,
        "wants_market_overview": bool(wants_market),
        "raw_text": raw,
    }
