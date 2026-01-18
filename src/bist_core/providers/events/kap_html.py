from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
import os
from pathlib import Path
from typing import List
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from bist_core.providers.events.base import EventsProvider


@dataclass
class _KapRow:
    cells: List[str]
    hrefs: List[str]


class KapHtmlEventsProvider(EventsProvider):
    name = "kap_html"

    def __init__(
        self,
        base_url: str = "https://www.kap.org.tr",
        url_template: str | None = None,
        timeout_s: int = 15,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        env_template = os.getenv("BIST_KAP_EVENTS_URL_TEMPLATE")
        self.url_template = url_template or env_template or "/kap/events/{day}"
        self.timeout_s = timeout_s
        self.source_url = ""

    def fetch_events_for_day(self, day: str) -> list[dict]:
        url = self._resolve_url(day)
        self.source_url = url
        request = Request(url, headers={"User-Agent": "bist-core/kap-html"})
        try:
            with urlopen(request, timeout=self.timeout_s) as resp:
                html = resp.read().decode("utf-8", errors="strict")
        except Exception as exc:
            return [{"error_marker": f"ProviderError:{exc.__class__.__name__}"}]

        rows = _KapTableParser().parse(html)
        if not rows:
            return [{"error_marker": "ParseError:NoRows"}]

        events: list[dict] = []
        for row in rows:
            if len(row.cells) < 4:
                events.append({"error_marker": "ParseError:MissingColumns"})
                continue
            ts_raw = row.cells[0]
            symbol = row.cells[1]
            kind = row.cells[2]
            title = row.cells[3]
            url_val = row.hrefs[0] if row.hrefs else None
            full_url = urljoin(self.base_url + "/", url_val) if url_val else None
            ts_iso = _normalize_ts(ts_raw)
            events.append(
                {
                    "symbol": symbol,
                    "ts": ts_iso or "",
                    "kind": kind,
                    "title": title,
                    "url": full_url,
                }
            )
        return events

    def _resolve_url(self, day: str) -> str:
        path = self.url_template.format(day=day)
        return urljoin(self.base_url + "/", path.lstrip("/"))


class _KapTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._rows: list[_KapRow] = []
        self._in_tr = False
        self._in_td = False
        self._cell_text: list[str] = []
        self._cells: list[str] = []
        self._hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "tr":
            self._in_tr = True
            self._cells = []
            self._hrefs = []
        elif tag == "td" and self._in_tr:
            self._in_td = True
            self._cell_text = []
        elif tag == "a" and self._in_tr and self._in_td:
            href = ""
            for key, value in attrs:
                if key == "href" and value:
                    href = value
                    break
            if href:
                self._hrefs.append(href)

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self._in_td:
            text = "".join(self._cell_text).strip()
            self._cells.append(text)
            self._in_td = False
        elif tag == "tr" and self._in_tr:
            if self._cells:
                self._rows.append(_KapRow(cells=self._cells, hrefs=self._hrefs))
            self._in_tr = False

    def handle_data(self, data: str) -> None:
        if self._in_td:
            self._cell_text.append(data)

    def parse(self, html: str) -> list[_KapRow]:
        self.feed(html)
        return self._rows


def _normalize_ts(raw: str) -> str | None:
    text = raw.strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%d.%m.%Y %H:%M"):
        try:
            dt = datetime.strptime(text, fmt)
            tz = timezone(timedelta(hours=3))
            return dt.replace(tzinfo=tz).isoformat()
        except ValueError:
            continue
    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            tz = timezone(timedelta(hours=3))
            dt = dt.replace(tzinfo=tz)
        return dt.isoformat()
    except Exception:
        return None
