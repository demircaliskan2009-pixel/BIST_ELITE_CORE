from __future__ import annotations

from dataclasses import asdict
import json
import platform
from pathlib import Path
import time
from typing import Any

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
    source_url = None
    raw_cache = None

    try:
        raw_events = provider.fetch_events_for_day(day)
        source_url = getattr(provider, "source_url", None)
        raw_cache = _provider_raw_cache(provider)
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

    events_sorted = sorted(events, key=lambda ev: (ev.symbol, ev.ts, ev.kind, ev.title))

    if atomic:
        _atomic_write_jsonl(out_path, events_sorted)
    else:
        _write_jsonl(out_path, events_sorted)

    error_list = sorted(errors, key=lambda item: item.get("idx", 0))
    manifest = {
        "schema_version": 1,
        "day": day,
        "provider": provider_name,
        "input": input_value,
        "source_url": source_url,
        "raw_cache": raw_cache,
        "out_path": str(out_path),
        "total_in": total_in,
        "accepted": accepted,
        "rejected": rejected,
        "duplicates": duplicates,
        "errors": error_list,
        "error_list": error_list,
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


def ingest_events_from_file(
    day: str,
    input_path: Path,
    outdir: Path,
    *,
    cli_args: dict | None = None,
) -> dict:
    start = time.perf_counter()
    raw_rows, total_in, errors = _read_events_input(input_path)
    existing_events, _ = eventstore.load_events_for_day(day, base_dir=outdir.parent)
    existing_list = [ev for items in existing_events.values() for ev in items]
    existing_keys = {eventstore.dedupe_key(ev) for ev in existing_list}
    seen_keys = set(existing_keys)

    accepted_events = []
    duplicates = 0

    for idx, row in raw_rows:
        event, err = eventstore.normalize_event(row, idx)
        if err:
            errors.append({"idx": idx, "error_marker": err})
            continue
        key = eventstore.dedupe_key(event)
        if key in seen_keys:
            duplicates += 1
            continue
        seen_keys.add(key)
        accepted_events.append(event)

    merged = eventstore.sort_events([*existing_list, *accepted_events])
    out_path = outdir / "events.jsonl"
    _atomic_write_jsonl(out_path, merged)

    error_list = sorted(errors, key=lambda item: item.get("idx", 0))
    manifest = {
        "schema_version": 1,
        "day": day,
        "input": str(input_path),
        "outdir": str(outdir),
        "total_in": total_in,
        "accepted": len(accepted_events),
        "rejected": len(errors),
        "duplicates": duplicates,
        "errors": error_list,
        "error_list": error_list,
        "runtime_ms": int((time.perf_counter() - start) * 1000),
        "provenance": {
            "cli_args": cli_args or {},
            "python": _python_version(),
            "platform": platform.platform(),
        },
    }
    atomic_write_json(outdir / "_manifest.json", manifest)
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


def _read_events_input(path: Path) -> tuple[list[tuple[int, dict]], int, list[dict]]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".jsonl":
        rows: list[tuple[int, dict]] = []
        errors: list[dict] = []
        total = 0
        for idx, line in enumerate(text.splitlines()):
            if not line.strip():
                continue
            total += 1
            try:
                row = json.loads(line)
            except Exception:
                errors.append({"idx": idx, "error_marker": "InvalidJSON"})
                continue
            if isinstance(row, dict):
                rows.append((idx, row))
            else:
                errors.append({"idx": idx, "error_marker": "InvalidRow"})
        return rows, total, errors

    try:
        data = json.loads(text)
    except Exception:
        return [], 0, [{"idx": 0, "error_marker": "InvalidJSON"}]
    if isinstance(data, list):
        rows: list[tuple[int, dict]] = []
        errors: list[dict] = []
        for idx, row in enumerate(data):
            if isinstance(row, dict):
                rows.append((idx, row))
            else:
                errors.append({"idx": idx, "error_marker": "InvalidRow"})
        return rows, len(data), errors
    return [], 0, [{"idx": 0, "error_marker": "InvalidJSON"}]


def _python_version() -> str:
    import sys

    return sys.version.split()[0]


def _provider_raw_cache(provider: Any) -> dict | None:
    """
    Best-effort extraction of provider-level raw cache/provenance.

    Providers may optionally expose:
    - raw_path: str | Path | None
    - raw_sha256: str | None
    - cache_only: bool | None
    """
    path_val = getattr(provider, "raw_path", None)
    if isinstance(path_val, Path):
        path_val = str(path_val)

    payload = {
        "path": path_val,
        "sha256": getattr(provider, "raw_sha256", None),
        "cache_only": getattr(provider, "cache_only", None),
    }
    if all(v is None for v in payload.values()):
        return None
    return payload
