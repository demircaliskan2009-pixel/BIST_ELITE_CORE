from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from typing import Any, Dict, List, Tuple


@dataclass
class InstrumentRecord:
    symbol: str
    isin: str | None
    name: str | None
    status: str
    listing_start: str | None
    listing_end: str | None
    market: str | None
    source: str
    ts: str
    error_marker: str | None = None


def parse_instruments(
    input_path: Path,
    source: str | None = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    rows = _read_rows(input_path)
    records: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []

    for idx, row in rows:
        record, err = _normalize_row(row, idx, source)
        if err:
            errors.append(err)
        records.append(record)

    return records, errors


def dedupe_instruments(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_symbol: Dict[str, Dict[str, Any]] = {}
    for record in records:
        symbol = record.get("symbol", "")
        current = by_symbol.get(symbol)
        if current is None:
            by_symbol[symbol] = record
            continue
        if _prefer(record, current):
            by_symbol[symbol] = record
    ordered = sorted(by_symbol.values(), key=lambda r: (r.get("symbol"), r.get("isin") or ""))
    return ordered


def atomic_write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    tmp_path = path.with_name(f"{path.name}.tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False))
            f.write("\n")
    tmp_path.replace(path)


def atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    tmp_path = path.with_name(f"{path.name}.tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    tmp_path.replace(path)


def build_manifest(
    day: str,
    outdir: Path,
    total: int,
    ok: int,
    errors: List[Dict[str, Any]],
    runtime_ms: int,
    provenance: Dict[str, Any],
    args_summary: Dict[str, Any],
) -> Dict[str, Any]:
    error_list = sorted(
        errors,
        key=lambda e: (e.get("idx", 0), e.get("symbol") or ""),
    )
    return {
        "schema_version": 1,
        "day": day,
        "outdir": str(outdir),
        "total": total,
        "ok": ok,
        "errors": len(error_list),
        "error_list": error_list,
        "runtime_ms": int(runtime_ms),
        "provenance": provenance,
        "args": args_summary,
    }


def load_instruments_jsonl(path: Path, source: str | None = None) -> List[Dict[str, Any]]:
    """
    Standard loader for instruments.jsonl. Returns list of dicts with normalized
    schema: symbol, isin, name, status, market, source, ts. Skips rows with missing symbol.
    Returns [] if path does not exist or is not a file.
    """
    if not path.exists() or not path.is_file():
        return []
    rows_tuples = _read_rows(path)
    out: List[Dict[str, Any]] = []
    for idx, row in rows_tuples:
        record, _ = _normalize_row(row, idx, source)
        if not (record.get("symbol") or "").strip():
            continue
        out.append({
            "symbol": record.get("symbol", ""),
            "isin": record.get("isin"),
            "name": record.get("name"),
            "status": record.get("status", "unknown"),
            "market": record.get("market"),
            "source": record.get("source", source or "offline_file"),
            "ts": record.get("ts"),
        })
    return out


def _read_rows(input_path: Path) -> List[Tuple[int, Dict[str, Any]]]:
    text = input_path.read_text(encoding="utf-8")
    if input_path.suffix.lower() == ".jsonl":
        rows: List[Tuple[int, Dict[str, Any]]] = []
        for idx, line in enumerate(text.splitlines()):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except Exception:
                rows.append((idx, {}))
                continue
            if isinstance(row, dict):
                rows.append((idx, row))
            else:
                rows.append((idx, {}))
        return rows

    try:
        data = json.loads(text)
    except Exception:
        return [(0, {})]
    if isinstance(data, list):
        rows = []
        for idx, row in enumerate(data):
            if isinstance(row, dict):
                rows.append((idx, row))
            else:
                rows.append((idx, {}))
        return rows
    return [(0, {})]


def _normalize_row(
    row: Dict[str, Any],
    idx: int,
    source: str | None,
) -> Tuple[Dict[str, Any], Dict[str, Any] | None]:
    error_marker = None
    symbol = _normalize_symbol(row.get("symbol"))
    if not symbol:
        error_marker = "SchemaError:missing_symbol"
    isin = _normalize_optional_upper(row.get("isin"))
    name = _normalize_optional_text(row.get("name"))
    status = _normalize_status(row.get("status"))
    listing_start = _normalize_date(row.get("listing_start"))
    listing_end = _normalize_date(row.get("listing_end"))
    market = _normalize_optional_upper(row.get("market"))
    ts = _normalize_ts(row.get("ts"))
    source_val = _normalize_optional_text(row.get("source")) or source or "offline_file"

    if listing_start and listing_end and listing_end < listing_start:
        error_marker = "SchemaError:invalid_listing_range"
    if not ts:
        error_marker = error_marker or "SchemaError:invalid_ts"
        ts = _normalize_ts(datetime.now(timezone.utc).isoformat())

    record = InstrumentRecord(
        symbol=symbol or "",
        isin=isin,
        name=name,
        status=status,
        listing_start=listing_start,
        listing_end=listing_end,
        market=market,
        source=source_val,
        ts=ts,
        error_marker=error_marker,
    )
    error = None
    if error_marker:
        error = {"symbol": record.symbol, "error_marker": error_marker, "idx": idx}
    return asdict(record), error


def _normalize_symbol(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    symbol = value.strip().upper()
    return symbol if symbol else None


def _normalize_optional_upper(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    text = value.strip().upper()
    return text or None


def _normalize_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _normalize_status(value: Any) -> str:
    allowed = {"active", "delisted", "unknown"}
    if not isinstance(value, str):
        return "unknown"
    val = value.strip().lower()
    return val if val in allowed else "unknown"


def _normalize_date(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    try:
        _ = datetime.fromisoformat(text)
    except Exception:
        return None
    return text


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
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except Exception:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return None


def _prefer(candidate: Dict[str, Any], current: Dict[str, Any]) -> bool:
    cand_active = candidate.get("listing_end") in (None, "")
    curr_active = current.get("listing_end") in (None, "")
    if cand_active != curr_active:
        return cand_active
    cand_end = candidate.get("listing_end") or ""
    curr_end = current.get("listing_end") or ""
    if cand_end != curr_end:
        return cand_end > curr_end
    cand_start = candidate.get("listing_start") or ""
    curr_start = current.get("listing_start") or ""
    if cand_start != curr_start:
        return cand_start > curr_start
    return (candidate.get("isin") or "") < (current.get("isin") or "")
