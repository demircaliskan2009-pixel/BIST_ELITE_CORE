"""
Build adjusted prices from snapshot(s) + canonical corporate actions.
Output: prices_raw.csv (instrument_id, date, close), prices_adj.csv (instrument_id, date, close_adj, adj_factor).

Backward adjustment formula (for dates before ex_date):
- split / bonus_issue / rights_issue: ratio R means 1 share becomes R shares; backward: close_adj = close / (1/R) = close * R.
  So cumulative ratio_factor = product(1/ratio) for these kinds; close_adj = raw_close / ratio_factor (raw_close after cash).
- reverse_split: ratio R < 1 means 1/R shares become 1; backward: close_adj = close * (1/R); same as 1/ratio in product.
- cash_dividend: subtract dividend from close then apply ratio factor: close_adj = (close - cash) / ratio_factor.
  So: cash_subtract = sum(cash) for all cash_dividend with ex_date > date; ratio_factor = product(1/ratio) for
  split/bonus_issue/rights_issue/reverse_split with ex_date > date; close_adj = (close - cash_subtract) / ratio_factor.
  adj_factor stored is ratio_factor (so close_adj = (close - cash_subtract) / adj_factor).
- Unknown kind in strict mode: fail-closed (error).
Deterministic: sort by (instrument_id, date).
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_KIND_RATIO = {"split", "bonus_issue", "rights_issue", "reverse_split"}
_KIND_CASH = {"cash_dividend"}
_KIND_KNOWN = _KIND_RATIO | _KIND_CASH | {"symbol_change", "isin_change", "other"}


def _date_lt(a: str, b: str) -> bool:
    try:
        return a < b
    except Exception:
        return False


def _load_snapshot_rows(snapshot_root: Path, day: str) -> List[Dict[str, Any]]:
    path = snapshot_root / day / "snapshot.csv"
    if not path.is_file():
        path = snapshot_root / (day + ".csv")
    if not path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    with path.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            sym = (r.get("symbol") or "").strip()
            close = r.get("close")
            if not sym or close is None or close == "":
                continue
            try:
                rows.append({"symbol": sym, "date": day, "close": float(close)})
            except (TypeError, ValueError):
                continue
    return rows


def _load_canonical_actions(path: Path) -> List[Dict[str, Any]]:
    """Load canonical actions from JSONL or corporate_actions.csv (schema v1)."""
    if not path.is_file():
        return []
    if path.suffix.lower() == ".csv":
        out: List[Dict[str, Any]] = []
        with path.open(newline="", encoding="utf-8") as f:
            rdr = csv.DictReader(f)
            for row in rdr:
                r = dict(row)
                for k in ("ratio", "cash"):
                    if k not in r or r[k] in (None, ""):
                        r[k] = None
                    else:
                        try:
                            r[k] = float(r[k])
                        except (TypeError, ValueError):
                            r[k] = None
                out.append(r)
        return out
    out = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out


def _adj_factor_and_close(
    instrument_id: str,
    date_val: str,
    close: float,
    actions_by_id: Dict[str, List[Dict[str, Any]]],
    strict: bool,
) -> Tuple[float, float, Optional[str]]:
    """
    Returns (close_adj, adj_factor, error). Backward: cash_subtract then ratio_factor.
    close_adj = (close - cash_subtract) / ratio_factor; adj_factor = ratio_factor.
    """
    actions = [a for a in actions_by_id.get(instrument_id, []) if _date_lt(date_val, a.get("ex_date", ""))]
    actions.sort(key=lambda a: a.get("ex_date", ""))
    cash_subtract = 0.0
    ratio_factor = 1.0
    for a in actions:
        kind = (a.get("kind") or "other").strip()
        if kind in _KIND_CASH:
            c = a.get("cash")
            if c is not None:
                cash_subtract += float(c)
        elif kind in _KIND_RATIO:
            r = a.get("ratio")
            if r is not None and float(r) != 0:
                ratio_factor *= 1.0 / float(r)
        elif kind in {"symbol_change", "isin_change", "other"}:
            pass
        elif strict:
            return 0.0, 1.0, f"unknown_kind:{kind}"
    raw = close - cash_subtract
    close_adj = raw / ratio_factor if ratio_factor != 0 else raw
    return close_adj, ratio_factor, None


def build_adjusted_prices(
    snapshot_root: Path,
    days: List[str],
    canonical_actions_path: Path,
    symbol_to_id: Dict[str, str],
    out_dir: Path,
    strict: bool = False,
) -> Tuple[int, List[str]]:
    """
    Build prices_raw.csv and prices_adj.csv in out_dir. Returns (error_count, notes).
    Raw: instrument_id, date, close. Adj: instrument_id, date, close_adj, adj_factor.
    """
    notes: List[str] = []
    all_raw: List[Dict[str, Any]] = []
    for day in days:
        for row in _load_snapshot_rows(snapshot_root, day):
            sym = (row.get("symbol") or "").strip().upper()
            iid = symbol_to_id.get(sym)
            if not iid:
                continue
            all_raw.append({
                "instrument_id": iid,
                "date": row["date"],
                "close": row["close"],
            })
    all_raw.sort(key=lambda r: (r.get("instrument_id", ""), r.get("date", "")))

    actions = _load_canonical_actions(canonical_actions_path)
    actions_by_id: Dict[str, List[Dict[str, Any]]] = {}
    for a in actions:
        iid = (a.get("instrument_id") or "").strip()
        if iid:
            actions_by_id.setdefault(iid, []).append(a)

    raw_rows: List[Dict[str, Any]] = []
    adj_rows: List[Dict[str, Any]] = []
    errors = 0
    for r in all_raw:
        iid = r["instrument_id"]
        date_val = r["date"]
        close = float(r["close"])
        raw_rows.append({"instrument_id": iid, "date": date_val, "close": close})
        close_adj, adj_factor, err = _adj_factor_and_close(
            iid, date_val, close, actions_by_id, strict
        )
        if err:
            notes.append(err)
            errors += 1
        adj_rows.append({
            "instrument_id": iid,
            "date": date_val,
            "close_adj": round(close_adj, 6),
            "adj_factor": round(adj_factor, 6),
        })

    out_dir.mkdir(parents=True, exist_ok=True)
    raw_path = out_dir / "prices_raw.csv"
    adj_path = out_dir / "prices_adj.csv"
    with raw_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["instrument_id", "date", "close"])
        w.writeheader()
        w.writerows(raw_rows)
    with adj_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["instrument_id", "date", "close_adj", "adj_factor"])
        w.writeheader()
        w.writerows(adj_rows)
    return errors, notes

