from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

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
    if base_dir is None:
        env_base = os.getenv("BIST_CORE_EVENTS_DIR")
        base = Path(env_base) if env_base else config.REPO_ROOT / "data" / "events"
    else:
        base = Path(base_dir)
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
    symbol = row.get("symbol")
    ts = row.get("ts")
    kind = row.get("kind")
    title = row.get("title")
    if not all(isinstance(v, str) and v.strip() for v in [symbol, ts, kind, title]):
        return None, f"SchemaError:row={idx} missing required fields"
    try:
        _ = datetime.fromisoformat(ts)
    except Exception:
        return None, f"SchemaError:row={idx} invalid ts"
    url = row.get("url")
    if url is not None and not isinstance(url, str):
        return None, f"SchemaError:row={idx} invalid url"
    tags = row.get("tags")
    if tags is not None and (
        not isinstance(tags, list) or not all(isinstance(t, str) for t in tags)
    ):
        return None, f"SchemaError:row={idx} invalid tags"
    payload = row.get("payload")
    if payload is not None and not isinstance(payload, dict):
        return None, f"SchemaError:row={idx} invalid payload"

    return (
        EventRecord(
            symbol=symbol,
            ts=ts,
            kind=kind,
            title=title,
            url=url,
            tags=tags,
            payload=payload,
        ),
        None,
    )


def _sort_events(events: List[EventRecord]) -> List[EventRecord]:
    def key(ev: EventRecord) -> str:
        return ev.ts

    return sorted(events, key=key, reverse=True)
