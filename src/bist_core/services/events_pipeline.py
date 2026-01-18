from __future__ import annotations

from dataclasses import asdict
import json
import platform
from pathlib import Path
import time

from bist_core.providers.events.base import EventsProvider
from bist_core.services import eventstore
from bist_core.services.dossier import atomic_write_json


def build_events_jsonl_for_day(
    day: str,
    provider: EventsProvider,
    out_path: Path,
    *,
    atomic: bool = True,
) -> dict:
    start = time.perf_counter()
    errors: list[dict] = []
    raw_events: list[dict] = []
    provider_name = getattr(provider, "name", provider.__class__.__name__)
    input_value = str(getattr(provider, "path", ""))

    try:
        raw_events = provider.fetch_events_for_day(day)
    except Exception as exc:
        errors.append({"idx": -1, "error_marker": f"ProviderError:{exc.__class__.__name__}"})

    total_in = len(raw_events)
    accepted = 0
    rejected = 0
    duplicates = 0

    seen_keys: set[tuple[str, str, str, str]] = set()
    events = []

    for idx, row in enumerate(raw_events):
        event, err = eventstore.normalize_event(row, idx)
        if err:
            errors.append({"idx": idx, "error_marker": err})
            rejected += 1
            continue
        key = eventstore.dedupe_key(event)
        if key in seen_keys:
            duplicates += 1
            continue
        seen_keys.add(key)
        events.append(event)
        accepted += 1

    events_sorted = sorted(
        events, key=lambda ev: (ev.symbol, ev.ts, ev.kind, ev.title)
    )

    if atomic:
        _atomic_write_jsonl(out_path, events_sorted)
    else:
        _write_jsonl(out_path, events_sorted)

    manifest = {
        "schema_version": 1,
        "day": day,
        "provider": provider_name,
        "input": input_value,
        "out_path": str(out_path),
        "total_in": total_in,
        "accepted": accepted,
        "rejected": rejected,
        "duplicates": duplicates,
        "errors": errors,
        "runtime_ms": int((time.perf_counter() - start) * 1000),
        "provenance": {
            "cli_args": {},
            "python": _python_version(),
            "platform": platform.platform(),
        },
    }
    manifest_path = out_path.parent / "_manifest.json"
    atomic_write_json(manifest_path, manifest)
    return manifest


def _atomic_write_jsonl(path: Path, events: list) -> None:
    tmp_path = path.with_name(f"{path.name}.tmp")
    _write_jsonl(tmp_path, events)
    tmp_path.replace(path)


def _write_jsonl(path: Path, events: list) -> None:
    with path.open("w", encoding="utf-8") as f:
        for event in events:
            f.write(json.dumps(asdict(event), ensure_ascii=False))
            f.write("\n")


def _python_version() -> str:
    import sys

    return sys.version.split()[0]
