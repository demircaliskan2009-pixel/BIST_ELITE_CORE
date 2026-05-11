from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from bist_core import config


@dataclass
class EventRecord:
    symbol: str
    ts: str
    kind: str
    title: str
    url: str | None = None
    tags: List[str] | None = None
    payload: Dict[str, Any] | None = None


def load_events_for_day(
    day: str,
    base_dir: Path | str | None = None,
) -> Tuple[Dict[str, List[EventRecord]], List[str]]:
    base = _events_base_dir(base_dir)
    path = base / day / "events.jsonl"
    if not path.exists():
        return {}, []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception as exc:
        return {}, [f"SchemaError:{exc.__class__.__name__}"]

    events_by_symbol: Dict[str, List[EventRecord]] = {}
    errors: List[str] = []
    for idx, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except Exception as exc:
            errors.append(f"SchemaError:line={idx} {exc.__class__.__name__}")
            continue
        event, err = _parse_event_row(row, idx)
        if err is not None:
            errors.append(err)
            continue
        if event.ts[:10] > day:
            errors.append(f"EventLeakage:future_ts:row={idx} ts={event.ts} day={day}")
            continue
        events_by_symbol.setdefault(event.symbol, []).append(event)

    for symbol, events in events_by_symbol.items():
        events_by_symbol[symbol] = _sort_events(events)

    return events_by_symbol, errors


def load_events_for_symbol_day(
    symbol: str,
    day: str,
    base_dir: Path | str | None = None,
) -> Tuple[List[EventRecord], List[str]]:
    events_by_symbol, errors = load_events_for_day(day, base_dir=base_dir)
    return events_by_symbol.get(symbol, []), errors


def _parse_event_row(row: Any, idx: int) -> Tuple[EventRecord | None, str | None]:
    if not isinstance(row, dict):
        return None, f"SchemaError:row={idx} not a dict"
    symbol = _normalize_symbol(row.get("symbol"))
    ts = _normalize_ts(row.get("ts"))
    kind = row.get("kind")
    title = row.get("title")
    if not symbol or not kind or not title or not ts:
        return None, f"SchemaError:row={idx} missing required fields"
    if not isinstance(kind, str) or not kind.strip():
        return None, f"SchemaError:row={idx} invalid kind"
    if not isinstance(title, str) or not title.strip():
        return None, f"SchemaError:row={idx} invalid title"
    url = row.get("url")
    if url is not None and not isinstance(url, str):
        return None, f"SchemaError:row={idx} invalid url"
    tags = row.get("tags")
    if tags is not None and (not isinstance(tags, list) or not all(isinstance(t, str) for t in tags)):
        return None, f"SchemaError:row={idx} invalid tags"
    payload = row.get("payload")
    if payload is not None and not isinstance(payload, dict):
        return None, f"SchemaError:row={idx} invalid payload"

    return (
        EventRecord(
            symbol=symbol,
            ts=ts,
            kind=kind.strip(),
            title=title.strip(),
            url=url,
            tags=tags,
            payload=payload,
        ),
        None,
    )


def _sort_events(events: List[EventRecord]) -> List[EventRecord]:
    def key(ev: EventRecord) -> Tuple[str, str, str]:
        return (ev.ts, ev.kind, ev.title)

    return sorted(events, key=key, reverse=True)


def _events_base_dir(base_dir: Path | str | None) -> Path:
    if base_dir is None:
        env_base = os.getenv("BIST_CORE_EVENTS_DIR")
        return Path(env_base) if env_base else config.REPO_ROOT / "data" / "eod" / "events"
    return Path(base_dir)


def _normalize_symbol(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    symbol = value.strip().upper()
    return symbol if symbol else None


def _normalize_ts(value: Any) -> str | None:
    if isinstance(value, (int, float)):
        ts_val = float(value)
        if ts_val > 1e12:
            ts_val = ts_val / 1000.0
        try:
            dt = datetime.fromtimestamp(ts_val, tz=timezone.utc)
        except Exception:
            return None
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            dt = _parse_iso(raw)
        except Exception:
            return None
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return None


def _parse_iso(value: str) -> datetime:
    if value.endswith("Z"):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def dedupe_key(event: EventRecord) -> tuple[str, str, str, str]:
    return (event.symbol, event.ts, event.kind, event.title)


def sort_events(events: Iterable[EventRecord]) -> List[EventRecord]:
    def key(ev: EventRecord) -> tuple[str, str, str, str]:
        return (ev.ts, ev.symbol, ev.kind, ev.title)

    return sorted(events, key=key, reverse=True)


def normalize_event(row: Any, idx: int) -> Tuple[EventRecord | None, str | None]:
    return _parse_event_row(row, idx)
