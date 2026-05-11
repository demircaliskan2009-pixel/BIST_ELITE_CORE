"""KAP JSON API provider for BIST corporate disclosures.

Fetches disclosure data from KAP's REST API endpoint:
    POST https://www.kap.org.tr/tr/api/disclosure/members/byCriteria

Returns the same dict format as KapHtmlEventsProvider (symbol, ts, kind,
title, url) so the backfill pipeline normalizes identically.

Network contract:
    All HTTP is gated by BIST_CORE_ALLOW_NETWORK env var (default OFF).
    If network is disabled and no cache exists → error_marker record.
    The provider never bypasses the network gate.

Response caching:
    Raw JSON responses are cached to {cache_dir}/{day}.json for provenance.
    Cache is read-first: if cache file exists and cache_only=True, no HTTP.

API notes:
    - KAP API returns max 2000 records per request.
    - For single-day queries this is sufficient (~4-750 records/day).
    - stockCodes field can contain multiple tickers: "BLS, BLSMD".
    - publishDate format: "DD.MM.YYYY HH:MM:SS" (TRT implied).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Final
from urllib.error import HTTPError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

from bist_core import config as core_config
from bist_core.env import network_allowed
from bist_core.providers.events.base import EventsProvider

_TRT: Final = timezone(timedelta(hours=3))

# KAP disclosure detail URL template
_DISCLOSURE_URL_TEMPLATE: Final = "https://www.kap.org.tr/tr/Bildirim/{index}"

# KAP API endpoint
_API_ENDPOINT: Final = "https://www.kap.org.tr/tr/api/disclosure/members/byCriteria"

# Map KAP subject field to canonical kind (lowercase substring match)
_SUBJECT_KIND_MAP: Final[dict[str, str]] = {
    "finansal rapor": "earnings",
    "sorumluluk beyanı": "earnings",
    "faaliyet raporu": "earnings",
    "temettü": "dividend",
    "kâr dağıtım": "dividend",
    "kar dağıtım": "dividend",
    "kar payı": "dividend",
    "payların geri alınması": "buyback",
    "pay geri alım": "buyback",
    "sözleşme": "contract",
    "yatırım": "investment",
    "kapasite": "investment",
    "ortaklık": "partnership",
    "birleşme": "partnership",
    "yönetim kurulu": "management",
    "genel müdür": "management",
    "pay alım satım": "management",
    "bağımsız denetim": "regulatory",
    "mevzuat": "regulatory",
    "devre kesici": "regulatory",
    "kredi derecelendirme": "general_disclosure",
    "özel durum": "general_disclosure",
    "genel kurul": "general_disclosure",
    "sermaye artırım": "general_disclosure",
    "sermaye azaltım": "general_disclosure",
    "değerleme raporu": "general_disclosure",
    "ihraç tavan": "general_disclosure",
}


def _classify_subject(subject: str) -> str:
    """Map KAP subject string to canonical kind."""
    subj_lower = subject.lower()
    for keyword, kind in _SUBJECT_KIND_MAP.items():
        if keyword in subj_lower:
            return kind
    return "general_disclosure"


def _parse_publish_date(raw: str) -> str:
    """Convert 'DD.MM.YYYY HH:MM:SS' → ISO 8601 with TRT offset."""
    text = raw.strip()
    if not text:
        return ""
    for fmt in ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M"):
        try:
            dt = datetime.strptime(text, fmt)
            return dt.replace(tzinfo=_TRT).isoformat()
        except ValueError:
            continue
    return ""


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    tmp.write_bytes(data)
    tmp.replace(path)


class KapJsonApiProvider(EventsProvider):
    """Fetch disclosures from KAP REST API (JSON)."""

    name = "kap_json_api"

    def __init__(
        self,
        api_url: str = _API_ENDPOINT,
        timeout_s: int = 30,
        cache_dir: Path | None = None,
        cache_only: bool | None = None,
        max_retries: int = 5,
        base_backoff_s: float = 10.0,
    ) -> None:
        self.api_url = api_url
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self.base_backoff_s = base_backoff_s

        env_cache = os.getenv("BIST_KAP_CACHE_DIR")
        raw_root = os.getenv("BIST_KAP_RAW_DIR") or os.getenv("BIST_RAW_DIR")
        if cache_dir is not None:
            self.cache_dir = cache_dir
        elif env_cache:
            self.cache_dir = Path(env_cache)
        elif raw_root:
            self.cache_dir = Path(raw_root) / "kap_json"
        else:
            self.cache_dir = core_config.DATA_DIR / "raw" / "kap_json"

        if cache_only is None:
            self.cache_only = os.getenv("BIST_KAP_CACHE_ONLY", "0") == "1"
        else:
            self.cache_only = cache_only

        # Provenance tracking
        self.last_cache_path: str | None = None
        self.last_sha256: str | None = None

    def fetch_events_for_day(self, day: str) -> list[dict]:
        """Fetch disclosure events for a single date.

        Args:
            day: ISO date string (YYYY-MM-DD).

        Returns:
            List of dicts with keys: symbol, ts, kind, title, url.
            Error rows contain 'error_marker' key.
        """
        cache_path = self.cache_dir / f"{day}.json"
        self.last_cache_path = str(cache_path)
        self.last_sha256 = None

        raw_bytes = self._fetch_raw(day, cache_path)
        if raw_bytes is None:
            return []

        self.last_sha256 = _sha256_hex(raw_bytes)

        try:
            records = json.loads(raw_bytes.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            return [{"error_marker": f"ParseError:JSON:{exc.__class__.__name__}"}]

        if not isinstance(records, list):
            return [{"error_marker": "ParseError:NotArray"}]

        events: list[dict] = []
        for rec in records:
            stock_codes = rec.get("stockCodes") or ""
            publish_date = rec.get("publishDate") or ""
            subject = rec.get("subject") or ""
            summary = rec.get("summary") or ""
            disc_index = rec.get("disclosureIndex")

            ts_iso = _parse_publish_date(publish_date)
            kind = _classify_subject(subject)
            url = _DISCLOSURE_URL_TEMPLATE.format(index=disc_index) if disc_index else None

            # stockCodes can be comma-separated ("BLS, BLSMD")
            symbols = [s.strip().upper() for s in stock_codes.split(",") if s.strip()]
            if not symbols:
                # Fund or entity without stock code — skip
                continue

            title = summary or subject

            for sym in symbols:
                events.append({
                    "symbol": sym,
                    "ts": ts_iso,
                    "kind": kind,
                    "title": title,
                    "url": url,
                })

        return events

    def _fetch_raw(self, day: str, cache_path: Path) -> bytes | None:
        """Fetch raw JSON bytes from network or cache. Fail-closed."""
        # Network disabled → cache only
        if not network_allowed():
            if cache_path.exists():
                try:
                    return cache_path.read_bytes()
                except Exception:
                    return None
            # No cache, no network → fail-closed
            return None

        # Cache-only mode
        if self.cache_only:
            if cache_path.exists():
                try:
                    return cache_path.read_bytes()
                except Exception:
                    return None
            return None

        # Try cache first for idempotent re-runs
        if cache_path.exists() and cache_path.stat().st_size > 2:
            try:
                return cache_path.read_bytes()
            except Exception:
                pass

        # Fetch from API with retry on 429
        payload = json.dumps(
            {"fromDate": day, "toDate": day},
            separators=(",", ":"),
        ).encode("utf-8")

        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            request = Request(
                self.api_url,
                data=payload,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Content-Type": "application/json;charset=UTF-8",
                    "Accept": "application/json",
                },
            )

            try:
                with urlopen(request, timeout=self.timeout_s) as resp:
                    data = resp.read()
                # Success — cache and return
                _atomic_write_bytes(cache_path, data)
                return data
            except HTTPError as exc:
                last_exc = exc
                if exc.code == 429 and attempt < self.max_retries:
                    wait = self.base_backoff_s * (2 ** attempt)
                    logger.warning(
                        "KAP 429 rate-limit for %s, retry %d/%d in %.0fs",
                        day, attempt + 1, self.max_retries, wait,
                    )
                    time.sleep(wait)
                    continue
                # Non-retryable HTTP error
                break
            except Exception as exc:
                last_exc = exc
                break

        # All retries exhausted or non-retryable error
        logger.warning("KAP fetch failed for %s: %s", day, last_exc)
        if cache_path.exists():
            try:
                return cache_path.read_bytes()
            except Exception:
                return None
        return None
