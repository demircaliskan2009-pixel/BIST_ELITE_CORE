"""KAP historical disclosure backfill.

Fetches per-day disclosure events from KAP and writes flat JSONL to:
    {output_dir}/{date}.jsonl

One record per line (deterministic, sorted by ts desc then symbol/kind/title):
    {"event_id": "<sha256>", "kind": "...", "symbol": "ASELS",
     "title": "...", "ts": "2024-01-15T08:00:00+03:00", "url": "..."}

Required env vars
-----------------
    BIST_CORE_ALLOW_NETWORK=1           unlock network fetch (default: OFF)
    BIST_KAP_EVENTS_URL_TEMPLATE        URL path template with {day} placeholder
                                        Example: /tr/BDA/rest/bildirimler/{day}
                                        Must match whatever your KAP source returns in
                                        the expected HTML table format.

Optional env vars
-----------------
    BIST_KAP_EVENTS_DIR                 override output directory (default: data/events/)
    BIST_KAP_CACHE_DIR                  raw HTML cache dir (default: data/raw/kap_html/)
    BIST_KAP_CACHE_ONLY=1               never issue network requests; fail on cache miss

Network contract
----------------
All HTTP is performed by KapHtmlEventsProvider.fetch_events_for_day().
If BIST_CORE_ALLOW_NETWORK is not set, the provider falls back to local HTML cache.
If the cache is also missing, it returns an error_marker record; no exception is raised.
backfill_range() never bypasses this gate.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Iterator

from bist_core.env import network_allowed
from bist_core.providers.events.kap_api import KapJsonApiProvider
from bist_core.providers.events.kap_html import KapHtmlEventsProvider


# ---------------------------------------------------------------------------
# Public result type
# ---------------------------------------------------------------------------


class BackfillResult:
    """Outcome of fetching one trading day."""

    __slots__ = ("date_str", "events_written", "errors", "skipped", "source")

    def __init__(
        self,
        date_str: str,
        *,
        events_written: int = 0,
        errors: int = 0,
        skipped: bool = False,
        source: str = "network",
    ) -> None:
        self.date_str = date_str
        self.events_written = events_written
        self.errors = errors
        self.skipped = skipped
        self.source = source

    def to_dict(self) -> dict:
        return {
            "date": self.date_str,
            "events": self.events_written,
            "errors": self.errors,
            "skipped": self.skipped,
            "source": self.source,
        }

    def __repr__(self) -> str:
        return (
            f"BackfillResult(date={self.date_str!r}, events={self.events_written}, "
            f"errors={self.errors}, skipped={self.skipped}, source={self.source!r})"
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _trading_days(start: date, end: date) -> Iterator[str]:
    """Yield ISO date strings Mon-Fri in [start, end] (inclusive).

    Uses weekday filter only. KAP will return empty/error for official holidays —
    those are recorded as 0-event days and skipped on resume.
    """
    cur = start
    while cur <= end:
        if cur.weekday() < 5:  # 0=Mon … 4=Fri
            yield cur.isoformat()
        cur += timedelta(days=1)


def _event_id(symbol: str, ts: str, kind: str, title: str) -> str:
    """Deterministic sha256 dedup key."""
    canonical = "\t".join([symbol, ts, kind, title])
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _normalize_raw(raw: dict) -> dict | None:
    """Convert KapHtmlEventsProvider output dict to canonical event record.

    Returns None for error_marker rows or records with missing required fields.
    """
    if "error_marker" in raw:
        return None
    symbol = (raw.get("symbol") or "").strip().upper()
    ts = (raw.get("ts") or "").strip()
    kind = (raw.get("kind") or "").strip()
    title = (raw.get("title") or "").strip()
    if not symbol or not ts or not kind or not title:
        return None
    url = raw.get("url")
    if url is not None and not isinstance(url, str):
        url = None
    return {
        "event_id": _event_id(symbol, ts, kind, title),
        "symbol": symbol,
        "ts": ts,
        "kind": kind,
        "title": title,
        "url": url,
    }


def _stable_sort_key(ev: dict) -> tuple:
    return (ev["ts"], ev["symbol"], ev["kind"], ev["title"])


def _atomic_write_jsonl(path: Path, records: list[dict]) -> None:
    """Write records to JSONL atomically (tmp + rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
    tmp.replace(path)


def _resolve_output_dir(output_dir: Path | str | None) -> Path:
    if output_dir is not None:
        return Path(output_dir)
    env_dir = os.getenv("BIST_KAP_EVENTS_DIR")
    if env_dir:
        return Path(env_dir)
    from bist_core import config as _cfg  # lazy import to keep module importable standalone

    return _cfg.REPO_ROOT / "data" / "events"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def backfill_range(
    start: date | str,
    end: date | str,
    output_dir: Path | str | None = None,
    *,
    resume: bool = True,
    min_delay_s: float = 0.5,
    base_url: str = "https://www.kap.org.tr",
    url_template: str | None = None,
    timeout_s: int = 20,
    use_json_api: bool = True,
    max_consecutive_empty: int = 0,
) -> list[BackfillResult]:
    """Backfill KAP events for [start, end] date range (trading days only).

    Args
    ----
    start, end      : Date range inclusive. YYYY-MM-DD string or date object.
    output_dir      : Where to write {date}.jsonl. Defaults to data/events/.
    resume          : Skip dates whose output file already exists (default True).
    min_delay_s     : Minimum seconds between HTTP requests (default 0.5).
    base_url        : KAP base URL. Default: https://www.kap.org.tr
    url_template    : URL path template. Overrides BIST_KAP_EVENTS_URL_TEMPLATE.
                      Must contain {day} placeholder.
    timeout_s       : Per-request HTTP timeout in seconds (default 20).
    use_json_api    : Use KAP JSON REST API (default True). If False, uses
                      the legacy HTML scraper.
    max_consecutive_empty : Abort after N consecutive 0-event, 0-byte fetches
                            (rate-limit detection). 0 = disabled.

    Returns
    -------
    List of BackfillResult, one per trading day attempted.
    """
    if isinstance(start, str):
        start = date.fromisoformat(start)
    if isinstance(end, str):
        end = date.fromisoformat(end)

    out_dir = _resolve_output_dir(output_dir)

    if use_json_api:
        provider = KapJsonApiProvider(timeout_s=timeout_s)
    else:
        provider = KapHtmlEventsProvider(
            base_url=base_url,
            url_template=url_template,
            timeout_s=timeout_s,
        )

    results: list[BackfillResult] = []
    last_request_ts: float = 0.0
    consecutive_empty: int = 0

    for day_str in _trading_days(start, end):
        out_path = out_dir / f"{day_str}.jsonl"

        # Resume: skip if file already exists and is non-empty
        if resume and out_path.exists() and out_path.stat().st_size > 0:
            results.append(BackfillResult(day_str, skipped=True, source="resume"))
            consecutive_empty = 0
            continue

        # Rate limiting: enforce minimum inter-request delay
        elapsed = time.monotonic() - last_request_ts
        if elapsed < min_delay_s:
            time.sleep(min_delay_s - elapsed)

        raw_events = provider.fetch_events_for_day(day_str)
        last_request_ts = time.monotonic()

        source = "network" if network_allowed() else "html_cache"

        error_count = 0
        clean_events: list[dict] = []
        seen_ids: set[str] = set()

        for raw in raw_events:
            if "error_marker" in raw:
                error_count += 1
                continue
            ev = _normalize_raw(raw)
            if ev is None:
                error_count += 1
                continue
            eid = ev["event_id"]
            if eid in seen_ids:
                continue
            seen_ids.add(eid)
            clean_events.append(ev)

        # Stable sort: ts desc, then symbol / kind / title asc
        clean_events.sort(key=_stable_sort_key, reverse=True)

        # Only write file if we got events (avoid empty placeholders from 429s)
        if clean_events:
            _atomic_write_jsonl(out_path, clean_events)
            consecutive_empty = 0
        else:
            consecutive_empty += 1

        results.append(
            BackfillResult(
                day_str,
                events_written=len(clean_events),
                errors=error_count,
                source=source,
            )
        )

        # Abort on persistent rate-limiting (consecutive empty fetches)
        if max_consecutive_empty > 0 and consecutive_empty >= max_consecutive_empty:
            break

    return results


def load_events_for_date(
    day: str,
    output_dir: Path | str | None = None,
) -> list[dict]:
    """Load normalized event records for a single date from flat JSONL.

    Returns empty list if file does not exist.
    """
    out_dir = _resolve_output_dir(output_dir)
    path = out_dir / f"{day}.jsonl"
    if not path.exists():
        return []
    records: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


__all__ = ["backfill_range", "load_events_for_date", "BackfillResult"]
