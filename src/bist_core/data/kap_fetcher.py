"""KAP RSS fetch — deterministic, fail-closed; network only when explicitly allowed."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from bist_core.env import network_allowed

KAP_RSS_URL = "https://www.kap.org.tr/tr/api/rss"

# BIST-style tickers: 3–6 uppercase letters (ASCII; optional .IS suffix stripped before match)
_SYMBOL_RE = re.compile(r"\b([A-Z]{3,6})\b")


def _strip_ns(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def _text(el: ET.Element | None) -> str:
    if el is None or el.text is None:
        return ""
    return str(el.text).strip()


def _parse_pub_ts(pub: str) -> int:
    """RFC 2822 / RFC 1123 date string → unix seconds; fail-closed → 0."""
    if not pub or not isinstance(pub, str):
        return 0
    s = pub.strip()
    if not s:
        return 0
    try:
        dt = parsedate_to_datetime(s)
        if dt is None:
            return 0
        return int(dt.timestamp())
    except (TypeError, ValueError, OSError):
        return 0


def _extract_symbol(title: str) -> str:
    """Fail-safe: first BIST-like token from title, else empty."""
    if not title or not isinstance(title, str):
        return ""
    t = title.upper().replace("İ", "I")
    # Normalize common Turkish İ → I for ASCII match
    m = _SYMBOL_RE.search(t)
    if not m:
        return ""
    return str(m.group(1)).strip()


def fetch_kap_rss() -> list[dict[str, Any]]:
    """
    Fetch KAP RSS feed and return normalized items.

    Returns [] when ``BIST_CORE_ALLOW_NETWORK`` is not enabled (offline default),
    on HTTP/XML/network errors, or empty feed.

    Each item: ``title``, ``symbol``, ``timestamp`` (unix int), ``raw`` (description or link).
    """
    if not network_allowed():
        return []

    req = Request(
        KAP_RSS_URL,
        headers={"User-Agent": "BIST_ELITE_CORE/1.0 (kap_fetcher; rss)"},
        method="GET",
    )
    try:
        with urlopen(req, timeout=20) as resp:
            raw = resp.read()
    except (HTTPError, URLError, TimeoutError, OSError):
        return []

    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return []

    out: list[dict[str, Any]] = []
    for el in root.iter():
        if _strip_ns(el.tag) != "item":
            continue
        title = ""
        link = ""
        desc = ""
        pub = ""
        for child in list(el):
            tag = _strip_ns(child.tag)
            if tag == "title":
                title = _text(child)
            elif tag == "link":
                link = _text(child)
            elif tag == "description":
                desc = _text(child)
            elif tag == "pubDate":
                pub = _text(child)

        ts = _parse_pub_ts(pub)
        sym = _extract_symbol(title)
        if not sym or ts <= 0:
            continue
        raw_text = desc if desc else link
        if not raw_text:
            raw_text = title

        out.append(
            {
                "title": str(title),
                "symbol": str(sym),
                "timestamp": int(ts),
                "raw": str(raw_text),
            }
        )

    return out


__all__ = ["fetch_kap_rss", "KAP_RSS_URL"]
