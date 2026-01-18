from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import time
from typing import Any, Dict, List, Tuple


@dataclass
class TimelineEntry:
    symbol: str
    isin: str | None
    name: str | None
    status: str
    market: str | None
    canonical_symbol: str
    aliases: List[str]
    meta: Dict[str, Any]


def build_timeline(
    day: str,
    instruments_path: Path,
    actions_path: Path,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    instruments = _read_jsonl(instruments_path)
    actions = _read_jsonl(actions_path)
    errors: List[Dict[str, Any]] = []
    notes: List[str] = []

    alias_map: Dict[str, str] = {}
    resolved: Dict[str, Dict[str, Any]] = {}

    actions_sorted = sorted(
        actions,
        key=lambda a: (a.get("effective_date") or "", a.get("symbol") or "", a.get("kind") or ""),
    )

    for idx, action in enumerate(actions_sorted):
        kind = action.get("kind")
        if not _is_effective(action.get("effective_date"), day):
            continue
        if kind == "symbol_change":
            old_symbol = _norm_symbol(action.get("old_symbol"))
            new_symbol = _norm_symbol(action.get("new_symbol"))
            if not old_symbol or not new_symbol:
                errors.append({"code": "invalid_symbol_change", "msg": "missing symbol", "symbol": old_symbol or "", "idx": idx})
                continue
            if old_symbol in alias_map and alias_map[old_symbol] != new_symbol:
                errors.append({"code": "alias_conflict", "msg": "conflicting alias", "symbol": old_symbol, "idx": idx})
                continue
            alias_map[old_symbol] = new_symbol
        elif kind == "isin_change":
            symbol = _norm_symbol(action.get("symbol"))
            new_isin = _norm_isin(action.get("new_isin"))
            if symbol and new_isin:
                entry = resolved.get(symbol)
                if entry:
                    entry["isin"] = new_isin
            else:
                errors.append({"code": "invalid_isin_change", "msg": "missing isin", "symbol": symbol or "", "idx": idx})

    for old_symbol in list(alias_map.keys()):
        if _detect_cycle(old_symbol, alias_map):
            errors.append({"code": "alias_cycle", "msg": "cycle detected", "symbol": old_symbol, "idx": -1})

    for row in instruments:
        symbol = _norm_symbol(row.get("symbol"))
        if not symbol:
            errors.append({"code": "missing_symbol", "msg": "instrument missing symbol", "symbol": "", "idx": -1})
            continue
        target = _resolve_alias(symbol, alias_map)
        entry = resolved.get(target)
        if entry:
            aliases = set(entry.get("aliases", []))
        else:
            aliases = set()
        if symbol != target:
            aliases.add(symbol)
        resolved[target] = {
            "symbol": target,
            "isin": _norm_isin(row.get("isin")),
            "name": row.get("name"),
            "status": row.get("status") or "unknown",
            "market": row.get("market"),
            "canonical_symbol": target,
            "aliases": sorted(aliases),
            "meta": {"source": row.get("source"), "ts": row.get("ts")},
        }

    resolved_list = sorted(
        resolved.values(), key=lambda r: (r["symbol"], r.get("isin") or "")
    )

    output = {
        "schema_version": 1,
        "day": day,
        "resolved": resolved_list,
        "alias_map": alias_map,
        "errors": errors,
        "notes": notes,
    }
    return output, errors


def build_manifest(
    day: str,
    outdir: Path,
    errors: List[Dict[str, Any]],
    runtime_ms: int,
    args: Dict[str, Any],
) -> Dict[str, Any]:
    error_list = sorted(errors, key=lambda e: (e.get("idx", 0), e.get("symbol") or ""))
    return {
        "schema_version": 1,
        "day": day,
        "outdir": str(outdir),
        "errors": len(error_list),
        "error_list": error_list,
        "runtime_ms": int(runtime_ms),
        "provenance": {
            "cli_args": args,
            "python": _python_version(),
        },
    }


def write_timeline(outdir: Path, timeline: Dict[str, Any]) -> None:
    path = outdir / "timeline.json"
    tmp = path.with_name(f"{path.name}.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(timeline, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def write_manifest(outdir: Path, manifest: Dict[str, Any]) -> None:
    path = outdir / "_manifest.json"
    tmp = path.with_name(f"{path.name}.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def resolve_timeline(
    day: str,
    instruments_path: Path,
    actions_path: Path,
    outdir: Path,
    args: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    start = time.perf_counter()
    timeline, errors = build_timeline(day, instruments_path, actions_path)
    write_timeline(outdir, timeline)
    manifest = build_manifest(
        day, outdir, errors, int((time.perf_counter() - start) * 1000), args
    )
    write_manifest(outdir, manifest)
    return timeline, manifest


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _norm_symbol(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip().upper()
    return text or None


def _norm_isin(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip().upper()
    return text or None


def _is_effective(effective_date: Any, day: str) -> bool:
    if not isinstance(effective_date, str):
        return False
    try:
        return datetime.fromisoformat(effective_date) <= datetime.fromisoformat(day)
    except Exception:
        return False


def _resolve_alias(symbol: str, alias_map: Dict[str, str]) -> str:
    seen = set()
    current = symbol
    while current in alias_map and current not in seen:
        seen.add(current)
        current = alias_map[current]
    return current


def _detect_cycle(symbol: str, alias_map: Dict[str, str]) -> bool:
    seen = set()
    current = symbol
    while current in alias_map:
        if current in seen:
            return True
        seen.add(current)
        current = alias_map[current]
    return False


def _python_version() -> str:
    import sys

    return sys.version.split()[0]
