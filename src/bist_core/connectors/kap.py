"""
FAZ68: KAP connector v1 — ingest disclosures from fixture HTML/JSON into knowledge documents.
Stable schema: doc_id (sha256), source, published_at_utc, title, body, tickers[].
No network; fixture-first for tests.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone, timedelta
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List, Union

SOURCE_KAP = "kap"


def _normalize_ts_to_utc(raw: str) -> str:
    """Normalize timestamp string to ISO UTC (published_at_utc)."""
    text = (raw or "").strip()
    if not text:
        return ""
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%d.%m.%Y %H:%M"):
        try:
            dt = datetime.strptime(text.replace("Z", ""), fmt.replace("Z", ""))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone(timedelta(hours=3)))
            return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        except ValueError:
            continue
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    except Exception:
        return ""


def _doc_id_canonical(source: str, published_at_utc: str, title: str, tickers: List[str]) -> str:
    """Deterministic doc_id = sha256(canonical string)."""
    tickers_str = "|".join(sorted(tickers)) if tickers else ""
    canonical = "\t".join([source, published_at_utc, title, tickers_str])
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def normalize_to_knowledge_doc(
    *,
    source: str = SOURCE_KAP,
    published_at_utc: str,
    title: str,
    body: str = "",
    tickers: List[str],
) -> Dict[str, Any]:
    """Build one knowledge document with stable fields and doc_id (sha256)."""
    tickers_list = sorted(set(t for t in (tickers or []) if (t or "").strip()))
    doc_id = _doc_id_canonical(source, published_at_utc, title, tickers_list)
    return {
        "doc_id": doc_id,
        "source": source,
        "published_at_utc": published_at_utc,
        "title": (title or "").strip(),
        "body": (body or "").strip(),
        "tickers": tickers_list,
    }


# ---- HTML table parser (same shape as kap_sample.html) ----


class _KapTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._rows: List[List[str]] = []
        self._hrefs: List[str] = []
        self._in_tr = False
        self._in_td = False
        self._cell_text: List[str] = []
        self._cells: List[str] = []
        self._row_hrefs: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[tuple]) -> None:
        if tag == "tr":
            self._in_tr = True
            self._cells = []
            self._row_hrefs = []
        elif tag == "td" and self._in_tr:
            self._in_td = True
            self._cell_text = []
        elif tag == "a" and self._in_tr and self._in_td:
            for k, v in attrs:
                if k == "href" and v:
                    self._row_hrefs.append(v)
                    break

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self._in_td:
            self._cells.append("".join(self._cell_text).strip())
            self._in_td = False
        elif tag == "tr" and self._in_tr:
            if self._cells:
                self._rows.append(self._cells)
                self._hrefs.append(self._row_hrefs[0] if self._row_hrefs else "")
            self._in_tr = False

    def handle_data(self, data: str) -> None:
        if self._in_td:
            self._cell_text.append(data)

    def parse(self, html: str) -> List[tuple]:
        """Returns list of (cells, href) per row."""
        self.feed(html)
        out: List[tuple] = []
        for i, cells in enumerate(self._rows):
            href = self._hrefs[i] if i < len(self._hrefs) else ""
            out.append((cells, href))
        return out


def ingest_from_html(html: Union[str, bytes, Path]) -> List[Dict[str, Any]]:
    """
    Ingest disclosures from KAP-style HTML table (Ts, Symbol, Kind, Title).
    Returns list of knowledge documents (doc_id, source, published_at_utc, title, body, tickers[]).
    No network.
    """
    if isinstance(html, Path):
        html = html.read_text(encoding="utf-8")
    elif isinstance(html, bytes):
        html = html.decode("utf-8", errors="replace")
    parser = _KapTableParser()
    rows = parser.parse(html)
    docs: List[Dict[str, Any]] = []
    for cells, _href in rows:
        if len(cells) < 4:
            continue
        ts_raw, symbol, kind, title_cell = cells[0], cells[1], cells[2], cells[3]
        published_at_utc = _normalize_ts_to_utc(ts_raw)
        title = title_cell.strip() or ""
        tickers = [symbol.strip()] if (symbol or "").strip() else []
        doc = normalize_to_knowledge_doc(
            source=SOURCE_KAP,
            published_at_utc=published_at_utc,
            title=title,
            body=title,
            tickers=tickers,
        )
        docs.append(doc)
    return docs


def ingest_from_json(data: Union[Dict, List, Path]) -> List[Dict[str, Any]]:
    """
    Ingest disclosures from JSON: list of {ts or published_at_utc, symbol or tickers, title, body?}.
    Returns list of knowledge documents. No network.
    """
    if isinstance(data, Path):
        raw = json.loads(data.read_text(encoding="utf-8"))
    else:
        raw = data
    if isinstance(raw, dict) and "disclosures" in raw:
        items = raw["disclosures"]
    elif isinstance(raw, list):
        items = raw
    else:
        items = [raw] if isinstance(raw, dict) else []
    docs: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        ts = item.get("ts") or item.get("published_at_utc") or item.get("date") or ""
        if isinstance(ts, (int, float)):
            ts = str(ts)
        published_at_utc = _normalize_ts_to_utc(ts) if ts else ""
        if not published_at_utc and ts:
            published_at_utc = str(ts).strip()
        symbol = item.get("symbol")
        tickers = item.get("tickers")
        if tickers is None and symbol is not None:
            tickers = [symbol] if isinstance(symbol, str) else list(symbol) if symbol else []
        if not isinstance(tickers, list):
            tickers = [tickers] if tickers else []
        tickers = [str(t).strip() for t in tickers if (t or "").strip()]
        title = (item.get("title") or "").strip()
        body = (item.get("body") or title or "").strip()
        doc = normalize_to_knowledge_doc(
            source=item.get("source", SOURCE_KAP),
            published_at_utc=published_at_utc,
            title=title,
            body=body,
            tickers=tickers,
        )
        docs.append(doc)
    return docs
