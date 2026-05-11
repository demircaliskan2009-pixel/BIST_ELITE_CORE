from __future__ import annotations

import json
import os
import re
import time
from datetime import date as Date
from pathlib import Path
from typing import List, Optional

from bist_core.services import eventstore
from bist_core.services.advisor import build_advice_for_symbol
from bist_core.services.marketdata import MarketData


def build_dossier_for_symbol_day(
    symbol: str,
    day: Date | str,
    root: Optional[Path | str] = None,
    snapshot_hash: Optional[dict] = None,
) -> dict:
    base = Path(root) if root is not None else Path("data/eod/snapshots")
    day_str = day.isoformat() if isinstance(day, Date) else str(day)

    has_ohlcv, provider = _marketdata_meta(base, day_str)
    provenance = {"snapshot_root": str(base), "provider": provider}
    if snapshot_hash is not None:
        provenance["snapshot_hash"] = snapshot_hash
    events, events_errors = _load_events(symbol, day_str)
    events_payload = [_event_payload(ev) for ev in events][:20]

    try:
        advice = build_advice_for_symbol(symbol, day_str, root=base)
        error_marker = None
        if isinstance(advice.text, str) and "Güvenli mod" in advice.text:
            error_marker = "SafeMode"
        return {
            "schema_version": 1,
            "symbol": symbol,
            "day": day_str,
            "decision_raw": advice.decision_raw,
            "score": advice.score,
            "signals": advice.signals,
            "plan": advice.plan,
            "text": advice.text,
            "capabilities": {"ohlcv": bool(has_ohlcv)},
            "provenance": provenance,
            "error_marker": error_marker,
            "events": events_payload,
            "events_errors": events_errors,
        }
    except Exception as exc:
        err = exc.__class__.__name__
        return {
            "schema_version": 1,
            "symbol": symbol,
            "day": day_str,
            "decision_raw": "PASS",
            "score": 0.0,
            "signals": [],
            "plan": None,
            "text": (f"Güvenli mod: {err}. Veri veya karar üretilemedi; snapshot ve konfigürasyonu kontrol edin."),
            "capabilities": {"ohlcv": False},
            "provenance": provenance,
            "error_marker": err,
            "events": events_payload,
            "events_errors": events_errors,
        }


def build_dossiers_for_day(
    day: Date | str,
    root: Optional[Path | str] = None,
    symbols: Optional[List[str]] = None,
    regex: Optional[str] = None,
    limit: Optional[int] = None,
    snapshot_hash: Optional[dict] = None,
) -> tuple[List[dict], int, dict]:
    base = Path(root) if root is not None else Path("data/eod/snapshots")
    day_str = day.isoformat() if isinstance(day, Date) else str(day)

    try:
        md = MarketData(base)
        base_symbols = md.symbols(day_str)
    except Exception:
        base_symbols = []

    symbols = _filter_symbols(
        base_symbols,
        symbols=symbols,
        regex=regex,
        limit=limit,
    )

    start = time.perf_counter()
    has_ohlcv, provider = _marketdata_meta(base, day_str)
    provenance = {
        "snapshot_root": str(base),
        "provider": provider,
        "snapshot_meta": {
            "ohlcv": bool(has_ohlcv),
            "close_only": not bool(has_ohlcv),
        },
    }
    if snapshot_hash is not None:
        provenance["snapshot_hash"] = snapshot_hash

    dossiers: List[dict] = []
    for sym in symbols:
        dossiers.append(
            build_dossier_for_symbol_day(
                sym,
                day_str,
                root=base,
                snapshot_hash=snapshot_hash,
            )
        )
    runtime_ms = int((time.perf_counter() - start) * 1000)
    return dossiers, runtime_ms, provenance


def build_manifest(
    day: Date | str,
    outdir: Path | str,
    dossiers: List[dict],
    runtime_ms: int,
    provenance: dict,
) -> dict:
    day_str = day.isoformat() if isinstance(day, Date) else str(day)
    error_list = [
        {"symbol": d.get("symbol", "UNKNOWN"), "error_marker": d.get("error_marker")}
        for d in dossiers
        if d.get("error_marker")
    ]
    # Fail-closed (SafeMode with NoBars/NoDecision) is canonical: PASS, not a pipeline error
    errors = len([e for e in error_list if e.get("error_marker") != "SafeMode"])
    total = len(dossiers)
    return {
        "schema_version": 1,
        "day": day_str,
        "outdir": str(outdir),
        "total": total,
        "ok": total - errors,
        "errors": errors,
        "error_list": error_list,
        "runtime_ms": int(runtime_ms),
        "provenance": provenance,
    }


def atomic_write_json(path: Path, payload: dict) -> None:
    """Write JSON atomically. Retry replace on Windows (WinError 32)."""
    tmp_path = path.with_name(f"{path.name}.tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    max_attempts = 10
    for attempt in range(max_attempts):
        try:
            tmp_path.replace(path)
            return
        except (PermissionError, OSError):
            if attempt == max_attempts - 1:
                raise
            time.sleep(0.05 * (attempt + 1))


def _filter_symbols(
    base_symbols: List[str],
    symbols: Optional[List[str]] = None,
    regex: Optional[str] = None,
    limit: Optional[int] = None,
) -> List[str]:
    ordered = list(base_symbols)
    if symbols:
        requested = [s for s in symbols if s]
        requested_set = set(requested)
        ordered = [s for s in ordered if s in requested_set]
        missing = [s for s in requested if s not in set(ordered)]
        ordered.extend(missing)

    if regex:
        try:
            matcher = re.compile(regex)
            ordered = [s for s in ordered if matcher.search(s)]
        except re.error:
            ordered = []

    if isinstance(limit, int) and limit >= 0:
        ordered = ordered[:limit]

    return ordered


def _marketdata_meta(base: Path, day_str: str) -> tuple[bool, str | None]:
    provider = None
    has_ohlcv = False
    try:
        md = MarketData(base)
        provider = md._prov.__class__.__name__ if hasattr(md, "_prov") else None
        has_ohlcv = md.has_ohlcv(day_str)
    except Exception:
        has_ohlcv = False
    return has_ohlcv, provider


def _load_events(symbol: str, day_str: str) -> tuple[list[eventstore.EventRecord], list[str]]:
    try:
        return eventstore.load_events_for_symbol_day(symbol, day_str)
    except Exception as exc:
        return [], [f"EventStoreError:{exc.__class__.__name__}"]


def _event_payload(event: eventstore.EventRecord) -> dict:
    return {
        "ts": event.ts,
        "kind": event.kind,
        "title": event.title,
        "url": event.url,
    }
