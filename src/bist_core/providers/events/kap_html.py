from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
from html.parser import HTMLParser
import os
from pathlib import Path
from typing import List
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from bist_core import config as core_config
from bist_core.env import network_allowed
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
        raw_dir: Path | None = None,
        cache_only: bool | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        env_template = os.getenv("BIST_KAP_EVENTS_URL_TEMPLATE")
        self.url_template = url_template or env_template or "/kap/events/{day}"
        self.timeout_s = timeout_s
        self.source_url = ""
        
        # Raw HTML caching: store raw HTML for provenance/lineage
        # Precedence: raw_dir param > BIST_KAP_CACHE_DIR (direct) > BIST_KAP_RAW_DIR/BIST_RAW_DIR (append kap_html) > default
        cache_dir_env = os.getenv("BIST_KAP_CACHE_DIR")
        raw_root_env = os.getenv("BIST_KAP_RAW_DIR") or os.getenv("BIST_RAW_DIR")
        if raw_dir is not None:
            self.raw_dir = raw_dir
        elif cache_dir_env:
            self.raw_dir = Path(cache_dir_env)
        elif raw_root_env:
            self.raw_dir = Path(raw_root_env) / "kap_html"
        else:
            self.raw_dir = core_config.DATA_DIR / "raw" / "kap_html"
        
        # Fail-closed cache-only mode: only use cache (no network)
        # Override: cache_only param or BIST_KAP_CACHE_ONLY=1
        if cache_only is None:
            self.cache_only = os.getenv("BIST_KAP_CACHE_ONLY", "0") == "1"
        else:
            self.cache_only = cache_only
        
        # Fields for tracking last fetch provenance (can be added to events_pipeline manifest)
        self.raw_path: str | None = None
        self.raw_sha256: str | None = None

    def fetch_events_for_day(self, day: str) -> list[dict]:
        url = self._resolve_url(day)
        self.source_url = url
        raw_path = self.raw_dir / f"{day}.html"
        self.raw_path = str(raw_path)
        self.raw_sha256 = None

        # Network kill-switch: no urlopen; cache miss -> raise
        if not network_allowed():
            if not raw_path.exists():
                raise RuntimeError("KAP_CACHE_MISS_NETWORK_DISABLED")
            try:
                html_bytes = raw_path.read_bytes()
                self.raw_sha256 = _sha256_hex(html_bytes)
                html = html_bytes.decode("utf-8", errors="strict")
            except Exception as exc:
                return [{"error_marker": f"ProviderError:CacheRead:{exc.__class__.__name__}"}]
        # Cache-only mode: cache miss -> fail-closed marker
        elif self.cache_only:
            if not raw_path.exists():
                return [{"error_marker": "ProviderError:CacheMiss"}]
            try:
                html_bytes = raw_path.read_bytes()
                self.raw_sha256 = _sha256_hex(html_bytes)
                html = html_bytes.decode("utf-8", errors="strict")
            except Exception as exc:
                return [{"error_marker": f"ProviderError:CacheRead:{exc.__class__.__name__}"}]
        else:
            # Normal mode: fetch from network, cache atomically
            request = Request(url, headers={"User-Agent": "bist-core/kap-html"})
            try:
                with urlopen(request, timeout=self.timeout_s) as resp:
                    html_bytes = resp.read()
                _atomic_write_bytes(raw_path, html_bytes)
                self.raw_sha256 = _sha256_hex(html_bytes)
                html = html_bytes.decode("utf-8", errors="strict")
            except Exception as exc:
                # Network failure -> fallback to cache if present
                if raw_path.exists():
                    try:
                        html_bytes = raw_path.read_bytes()
                        self.raw_sha256 = _sha256_hex(html_bytes)
                        html = html_bytes.decode("utf-8", errors="strict")
                    except Exception as exc2:
                        return [{"error_marker": f"ProviderError:CacheRead:{exc2.__class__.__name__}"}]
                else:
                    return [{"error_marker": f"ProviderError:{exc.__class__.__name__}"}]

        try:
            rows = _KapTableParser().parse(html)
        except Exception as exc:
            return [{"error_marker": f"ParseError:HTMLParse:{exc.__class__.__name__}"}]
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


def _sha256_hex(data: bytes) -> str:
    """Compute SHA256 hex digest of bytes."""
    return hashlib.sha256(data).hexdigest()


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    """Atomically write bytes to file using temporary file + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    tmp.write_bytes(data)
    tmp.replace(path)
