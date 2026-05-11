from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple


@dataclass
class CorporateActionRecord:
    symbol: str
    effective_date: str
    kind: str
    ratio: float | None
    cash: float | None
    old_symbol: str | None
    new_symbol: str | None
    old_isin: str | None
    new_isin: str | None
    source: str
    ts: str
    error_marker: str | None = None


_KIND_ALLOWED = {
    "split",
    "reverse_split",
    "cash_dividend",
    "bonus_issue",
    "rights_issue",
    "symbol_change",
    "isin_change",
    "other",
}


def parse_actions(input_path: Path) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    rows = _read_rows(input_path)
    records: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    for idx, row in rows:
        record, err = _normalize_row(row, idx)
        records.append(record)
        if err:
            errors.append(err)
    return records, errors


def dedupe_actions(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: set[tuple] = set()
    deduped: List[Dict[str, Any]] = []
    for record in records:
        key = (
            record.get("effective_date"),
            record.get("symbol"),
            record.get("kind"),
            record.get("old_symbol"),
            record.get("new_symbol"),
            record.get("old_isin"),
            record.get("new_isin"),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(record)
    return sorted(deduped, key=lambda r: (r.get("effective_date"), r.get("symbol"), r.get("kind")))


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
        key=lambda e: (
            e.get("idx", 0),
            e.get("effective_date") or "",
            e.get("symbol") or "",
        ),
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
            rows.append((idx, row if isinstance(row, dict) else {}))
        return rows
    try:
        data = json.loads(text)
    except Exception:
        return [(0, {})]
    if isinstance(data, list):
        return [(idx, row if isinstance(row, dict) else {}) for idx, row in enumerate(data)]
    return [(0, {})]


def _normalize_row(row: Dict[str, Any], idx: int) -> Tuple[Dict[str, Any], Dict[str, Any] | None]:
    """Minimal CA schema: type (kind), ex_date (effective_date), ratio/amount (cash), symbol."""
    error_marker = None
    symbol = _normalize_symbol(row.get("symbol"))
    effective_date = _normalize_date(row.get("effective_date") or row.get("ex_date"))
    kind = _normalize_kind(row.get("kind") or row.get("type"))
    ratio = _normalize_ratio(row.get("ratio"))
    cash = _normalize_cash(row.get("cash") or row.get("amount"))
    old_symbol = _normalize_symbol(row.get("old_symbol"))
    new_symbol = _normalize_symbol(row.get("new_symbol"))
    old_isin = _normalize_optional_upper(row.get("old_isin"))
    new_isin = _normalize_optional_upper(row.get("new_isin"))
    source = _normalize_optional_text(row.get("source")) or "offline_file"
    ts = _normalize_ts(row.get("ts"))

    if not symbol:
        error_marker = "SchemaError:missing_symbol"
    if not effective_date:
        error_marker = error_marker or "SchemaError:invalid_effective_date"
    if not kind:
        error_marker = error_marker or "SchemaError:invalid_kind"

    if kind in {"split", "reverse_split", "bonus_issue", "rights_issue"}:
        if ratio is None or ratio <= 0:
            error_marker = error_marker or "SchemaError:invalid_ratio"
    if kind == "cash_dividend":
        if cash is None or cash < 0:
            error_marker = error_marker or "SchemaError:invalid_cash"
    if kind == "symbol_change":
        if not old_symbol or not new_symbol:
            error_marker = error_marker or "SchemaError:invalid_symbol_change"
    if kind == "isin_change":
        if not old_isin or not new_isin:
            error_marker = error_marker or "SchemaError:invalid_isin_change"

    if not ts:
        error_marker = error_marker or "SchemaError:invalid_ts"
        ts = _normalize_ts(datetime.now(timezone.utc).isoformat()) or ""

    record = CorporateActionRecord(
        symbol=symbol or "",
        effective_date=effective_date or "",
        kind=kind or "other",
        ratio=ratio,
        cash=cash,
        old_symbol=old_symbol,
        new_symbol=new_symbol,
        old_isin=old_isin,
        new_isin=new_isin,
        source=source,
        ts=ts,
        error_marker=error_marker,
    )
    error = None
    if error_marker:
        error = {
            "symbol": record.symbol,
            "effective_date": record.effective_date,
            "error_marker": error_marker,
            "idx": idx,
        }
    return asdict(record), error


def _normalize_symbol(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip().upper()
    return text or None


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


def _normalize_date(value: Any) -> str | None:
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


def _normalize_kind(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    return text if text in _KIND_ALLOWED else None


def _normalize_ratio(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _normalize_cash(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


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
