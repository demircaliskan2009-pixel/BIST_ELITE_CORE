"""
FAZ69: Instrument master refresh — merge new symbols/aliases from fixture dataset
into existing identity timeline deterministically (stable id, alias intervals).
No network.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


IDENTITY_TIMELINE_SCHEMA_VERSION = 1


def _norm(s: str) -> str:
    return (s or "").strip().upper()


def load_identity_timeline(path: Path | str) -> Dict[str, Any]:
    """
    Load existing identity timeline from JSON, or return empty default.
    Schema: identities: [{ id, symbol, aliases[], alias_intervals: [{ alias, valid_from, valid_to? }] }], alias_map: {}.
    """
    p = Path(path)
    if not p.is_file():
        return {
            "schema_version": IDENTITY_TIMELINE_SCHEMA_VERSION,
            "identities": [],
            "alias_map": {},
        }
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("identities", [])
            data.setdefault("alias_map", {})
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return {
        "schema_version": IDENTITY_TIMELINE_SCHEMA_VERSION,
        "identities": [],
        "alias_map": {},
    }


def save_identity_timeline(path: Path | str, timeline: Dict[str, Any]) -> None:
    """Write identity timeline JSON atomically."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(timeline, f, ensure_ascii=False, indent=2)
    tmp.replace(p)


def load_fixture_dataset(path: Path | str) -> List[Dict[str, Any]]:
    """
    Load fixture CSV (instrument_id, symbol, aliases) — same format as instrument_master.
    Returns list of { instrument_id, symbol, aliases: [] }.
    """
    p = Path(path)
    if not p.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    with p.open(newline="", encoding="utf-8") as f:
        rdr = csv.DictReader(f)
        fn = rdr.fieldnames or []
        has_id = "instrument_id" in fn
        has_symbol = "symbol" in fn
        if not has_symbol:
            return []
        for row in rdr:
            sym = _norm(row.get("symbol") or "")
            if not sym:
                continue
            iid = _norm(row.get("instrument_id") or "").strip() if has_id else ""
            if not iid:
                iid = f"sym_{sym}"
            aliases_raw = (row.get("aliases") or "").strip()
            aliases = [_norm(a) for a in aliases_raw.split(";") if _norm(a)]
            rows.append({"instrument_id": iid, "symbol": sym, "aliases": aliases})
    return rows


def merge_fixture_into_timeline(
    existing: Dict[str, Any],
    fixture_rows: List[Dict[str, Any]],
    effective_date: str = "",
) -> Dict[str, Any]:
    """
    Merge fixture rows into existing identity timeline deterministically.
    - Existing identities keep stable id; new aliases get alias_interval (valid_from=effective_date, valid_to=null).
    - New symbols get new identity with stable id (from fixture instrument_id).
    - alias_map: alias -> id, built from identities. Sorted for determinism.
    """
    identities_by_id: Dict[str, Dict[str, Any]] = {}
    for ent in existing.get("identities", []):
        raw_id = (ent.get("id") or "").strip()
        if raw_id:
            iid_key = _norm(raw_id)
            identities_by_id[iid_key] = {
                "id": iid_key,
                "symbol": _norm(ent.get("symbol", "")),
                "aliases": list(ent.get("aliases", [])),
                "alias_intervals": list(ent.get("alias_intervals", [])),
            }

    for row in fixture_rows:
        iid = _norm(row.get("instrument_id") or "") or f"sym_{_norm(row.get('symbol') or '')}"
        sym = _norm(row.get("symbol") or "")
        new_aliases = [a for a in row.get("aliases", []) if _norm(a)]
        if not sym:
            continue
        if not iid or iid == "sym_":
            iid = f"sym_{sym}"
        if iid in identities_by_id:
            ent = identities_by_id[iid]
            existing_aliases = set(ent["aliases"])
            for a in new_aliases:
                if a not in existing_aliases:
                    ent["aliases"].append(a)
                    ent["alias_intervals"].append(
                        {
                            "alias": a,
                            "valid_from": effective_date or "",
                            "valid_to": None,
                        }
                    )
                    existing_aliases.add(a)
            if sym not in existing_aliases and sym != ent["symbol"]:
                existing_aliases.add(sym)
                ent["aliases"].append(sym)
        else:
            alias_intervals = [{"alias": a, "valid_from": effective_date or "", "valid_to": None} for a in new_aliases]
            identities_by_id[iid] = {
                "id": iid,
                "symbol": sym,
                "aliases": sorted(set([sym] + new_aliases)),
                "alias_intervals": alias_intervals,
            }

    identities_list: List[Dict[str, Any]] = []
    for iid in sorted(identities_by_id.keys()):
        ent = identities_by_id[iid]
        ent["aliases"] = sorted(set(ent.get("aliases", [])))
        ent["alias_intervals"] = sorted(
            ent.get("alias_intervals", []),
            key=lambda x: (x.get("alias", ""), x.get("valid_from", "")),
        )
        identities_list.append(ent)

    alias_map: Dict[str, str] = {}
    for ent in identities_list:
        iid = ent["id"]
        alias_map[ent["symbol"]] = iid
        for a in ent.get("aliases", []):
            alias_map[a] = iid

    return {
        "schema_version": IDENTITY_TIMELINE_SCHEMA_VERSION,
        "identities": identities_list,
        "alias_map": dict(sorted(alias_map.items())),
    }


def refresh_instrument_master(
    existing_timeline_path: Path | str,
    fixture_path: Path | str,
    output_path: Path | str,
    effective_date: str = "",
) -> Tuple[Dict[str, Any], Optional[str]]:
    """
    Refresh step: load existing timeline (or empty), load fixture, merge, save to output_path.
    Returns (timeline, error). error is None on success.
    """
    existing_path = Path(existing_timeline_path)
    fixture_p = Path(fixture_path)
    out_p = Path(output_path)
    if not fixture_p.is_file():
        return load_identity_timeline(existing_path), "fixture_not_found"
    existing = load_identity_timeline(existing_path)
    fixture_rows = load_fixture_dataset(fixture_p)
    if not fixture_rows:
        return existing, None
    merged = merge_fixture_into_timeline(existing, fixture_rows, effective_date)
    save_identity_timeline(out_p, merged)
    return merged, None
