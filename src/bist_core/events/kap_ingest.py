"""
FAZ91: KAP HTML ingest -> events.json with hash (source HTML), source (path/label), deterministic event ids.
No network; file/string input only.
"""
from __future__ import annotations

import hashlib
import json
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List, Union

EVENTS_JSON_SCHEMA_VERSION = 1
SOURCE_KAP = "kap"


def _event_id_canonical(symbol: str, ts: str, kind: str, title: str) -> str:
    """Deterministic event id = sha256(symbol, ts, kind, title)."""
    canonical = "\t".join([str(symbol), str(ts), str(kind), str(title)])
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _normalize_ts(raw: str) -> str:
    """Normalize timestamp to ISO-like string for stable ids."""
    from datetime import datetime, timedelta, timezone

    text = (raw or "").strip()
    if not text:
        return ""
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%d.%m.%Y %H:%M"):
        try:
            dt = datetime.strptime(text, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone(timedelta(hours=3)))
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            continue
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return text


class _KapTableParser(HTMLParser):
    """Parse KAP-style HTML table: Ts, Symbol, Kind, Title (with optional <a href> in title cell)."""

    def __init__(self) -> None:
        super().__init__()
        self._rows: List[List[str]] = []
        self._hrefs: List[str] = []
        self._in_tr = False
        self._in_td = False
        self._cell_text: List[str] = []
        self._cells: List[str] = []
        self._row_hrefs: List[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
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
                self._rows.append(list(self._cells))
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


def ingest_kap_html(
    html: Union[str, bytes, Path],
    *,
    source: str = SOURCE_KAP,
) -> Dict[str, Any]:
    """
    Ingest KAP HTML into events.json payload: hash (of HTML), source, events (with deterministic id per row).
    No network. Same HTML -> same hash and same event ids.
    """
    if isinstance(html, Path):
        html_bytes = html.read_bytes()
        source_str = str(html) if source == SOURCE_KAP else source
    elif isinstance(html, bytes):
        html_bytes = html
        source_str = source
    else:
        html_bytes = html.encode("utf-8")
        source_str = source

    html_hash = hashlib.sha256(html_bytes).hexdigest()
    html_str = html_bytes.decode("utf-8", errors="replace")

    parser = _KapTableParser()
    rows = parser.parse(html_str)

    events: List[Dict[str, Any]] = []
    seen_ids: set[str] = set()
    for cells, href in rows:
        if len(cells) < 4:
            continue
        ts_raw, symbol, kind, title = cells[0], cells[1], cells[2], cells[3]
        symbol = (symbol or "").strip().upper()
        kind = (kind or "").strip()
        title = (title or "").strip()
        if not symbol or not kind or not title:
            continue
        ts = _normalize_ts(ts_raw)
        event_id = _event_id_canonical(symbol, ts, kind, title)
        if event_id in seen_ids:
            continue
        seen_ids.add(event_id)
        event: Dict[str, Any] = {
            "id": event_id,
            "symbol": symbol,
            "ts": ts,
            "kind": kind,
            "title": title,
        }
        if href:
            event["url"] = href
        events.append(event)

    # Stable order by (ts desc, symbol, kind, title)
    events.sort(key=lambda e: (e["ts"], e["symbol"], e["kind"], e["title"]), reverse=True)

    return {
        "schema_version": EVENTS_JSON_SCHEMA_VERSION,
        "hash": html_hash,
        "source": source_str,
        "events": events,
    }


def write_events_json(path: Path | str, data: Dict[str, Any]) -> Path:
    """Write events.json with deterministic key order."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
    tmp.replace(p)
    return p


__all__ = ["ingest_kap_html", "write_events_json", "EVENTS_JSON_SCHEMA_VERSION", "SOURCE_KAP"]
