"""Corporate actions canonicalization: event_id, instrument_id, ex_date, kind, ratio, cash, raw_source. Deterministic."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

# FAZ70: Canonical corporate_actions.csv schema v1 (column order for deterministic CSV).
CORPORATE_ACTIONS_CSV_SCHEMA_V1 = [
    "event_id",
    "instrument_id",
    "ex_date",
    "kind",
    "ratio",
    "cash",
    "raw_source",
]


def _event_id(instrument_id: str, ex_date: str, kind: str, ratio: Any, cash: Any) -> str:
    r = "" if ratio is None else str(ratio)
    c = "" if cash is None else str(cash)
    payload = f"{instrument_id}|{ex_date}|{kind}|{r}|{c}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def canonicalize_row(
    row: Dict[str, Any],
    symbol_to_id: Dict[str, str],
) -> Tuple[Dict[str, Any] | None, str | None]:
    """
    Build canonical record or error. Returns (canon_dict, error).
    Canonical: event_id, instrument_id, ex_date, kind, ratio(optional), cash(optional), raw_source(optional).
    """
    symbol = (row.get("symbol") or "").strip().upper()
    if not symbol:
        return None, "missing_symbol"
    instrument_id = symbol_to_id.get(symbol)
    if not instrument_id:
        return None, "unresolved_instrument_id"
    ex_date = (row.get("effective_date") or row.get("ex_date") or "").strip()
    if not ex_date:
        return None, "missing_ex_date"
    kind = (row.get("kind") or row.get("type") or "other").strip()
    ratio = row.get("ratio")
    if ratio is not None:
        try:
            ratio = float(ratio)
        except (TypeError, ValueError):
            ratio = None
    cash = row.get("cash") or row.get("amount")
    if cash is not None:
        try:
            cash = float(cash)
        except (TypeError, ValueError):
            cash = None
    raw_source = (row.get("source") or row.get("raw_source") or "").strip()
    event_id = _event_id(instrument_id, ex_date, kind, ratio, cash)
    canon = {
        "event_id": event_id,
        "instrument_id": instrument_id,
        "ex_date": ex_date,
        "kind": kind,
    }
    if ratio is not None:
        canon["ratio"] = ratio
    if cash is not None:
        canon["cash"] = cash
    if raw_source:
        canon["raw_source"] = raw_source
    return canon, None


def build_canonical(
    records: List[Dict[str, Any]],
    symbol_to_id: Dict[str, str],
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Canonicalize records; resolve symbol -> instrument_id via symbol_to_id.
    Returns (sorted canonical list by event_id, error_count). Deterministic.
    """
    canonical: List[Dict[str, Any]] = []
    errors = 0
    for row in records:
        canon, err = canonicalize_row(row, symbol_to_id)
        if err:
            errors += 1
            continue
        if canon:
            canonical.append(canon)
    canonical.sort(key=lambda r: (r.get("event_id", ""), r.get("ex_date", ""), r.get("instrument_id", "")))
    return canonical, errors


def write_canonical(out_path: Path, canonical: List[Dict[str, Any]]) -> None:
    """Write canonical records to JSONL (one JSON object per line). Deterministic order already applied."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_name(f"{out_path.name}.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for row in canonical:
            f.write(json.dumps(row, ensure_ascii=False))
            f.write("\n")
    tmp.replace(out_path)


def write_canonical_csv(out_path: Path, canonical: List[Dict[str, Any]]) -> None:
    """FAZ70: Write canonical records to corporate_actions.csv (schema v1). Deterministic column order."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_name(f"{out_path.name}.tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CORPORATE_ACTIONS_CSV_SCHEMA_V1, extrasaction="ignore")
        w.writeheader()
        for row in canonical:
            out_row = {}
            for k in CORPORATE_ACTIONS_CSV_SCHEMA_V1:
                v = row.get(k)
                if v is None or v == "":
                    out_row[k] = ""
                elif k in ("ratio", "cash") and not isinstance(v, (int, float)):
                    try:
                        out_row[k] = float(v)
                    except (TypeError, ValueError):
                        out_row[k] = ""
                else:
                    out_row[k] = v
            w.writerow(out_row)
    tmp.replace(out_path)


def canonicalize_actions_file(
    actions_path: Path,
    out_path: Path,
    symbol_to_id: Dict[str, str],
    out_csv_path: Path | None = None,
) -> Tuple[int, int]:
    """
    Read actions JSONL, canonicalize, write to out_path (JSONL). If out_csv_path set, also write CSV (schema v1).
    Returns (canonical_count, error_count).
    """
    if not actions_path.is_file():
        return 0, 0
    records: List[Dict[str, Any]] = []
    with actions_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except Exception:
                pass
    canonical, errors = build_canonical(records, symbol_to_id)
    write_canonical(out_path, canonical)
    if out_csv_path is not None:
        write_canonical_csv(out_csv_path, canonical)
    return len(canonical), errors


def _read_fixture_disclosures(path: Path) -> List[Dict[str, Any]]:
    """Read fixture disclosures from JSONL or CSV (symbol, effective_date/ex_date, kind, ratio, cash, source)."""
    if not path.is_file():
        return []
    suffix = path.suffix.lower()
    rows: List[Dict[str, Any]] = []
    if suffix == ".jsonl":
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
                if isinstance(r, dict):
                    rows.append(r)
            except Exception:
                continue
        return rows
    if suffix == ".csv":
        with path.open(newline="", encoding="utf-8") as f:
            rdr = csv.DictReader(f)
            for row in rdr:
                rows.append(dict(row))
        return rows
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [r for r in data if isinstance(r, dict)]
    except Exception:
        pass
    return []


def ingest_from_fixture_disclosures(
    disclosures_path: Path | str,
    symbol_to_id: Dict[str, str],
    outdir: Path | str,
    *,
    csv_filename: str = "corporate_actions.csv",
) -> Tuple[int, int]:
    """
    FAZ70: Ingest fixture disclosures -> canonical corporate_actions.csv (schema v1). Deterministic order + event_id.
    disclosures_path: JSONL or CSV with symbol, effective_date/ex_date, kind, ratio, cash, source.
    outdir: directory to write corporate_actions.csv. Returns (canonical_count, error_count).
    """
    p = Path(disclosures_path)
    out = Path(outdir)
    records = _read_fixture_disclosures(p)
    canonical, errors = build_canonical(records, symbol_to_id)
    out.mkdir(parents=True, exist_ok=True)
    write_canonical_csv(out / csv_filename, canonical)
    return len(canonical), errors
