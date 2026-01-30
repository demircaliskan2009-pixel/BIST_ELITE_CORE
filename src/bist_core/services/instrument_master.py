"""Instrument master gate: load CSV (instrument_id, symbol required; aliases optional) -> symbols set + meta; resolve_symbols for identity/aliases."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

from bist_core.services import snapshot_integrity


def load_instrument_master(path: Path | str) -> Tuple[Set[str], Dict[str, Any], Dict[str, str]]:
    """
    Load CSV with required 'instrument_id' and 'symbol' columns; optional 'aliases' (';' separated).
    Returns (symbols_set, meta, symbol_to_id).
    symbols_set: set of symbol strings, uppercase and stripped.
    meta: {"file": str, "sha256": str, "rows": int}.
    symbol_to_id: normalized_symbol -> instrument_id (for resolution); empty if instrument_id column missing.
    """
    p = Path(path)
    if not p.is_file():
        return set(), {"file": str(p), "sha256": "", "rows": 0}, {}
    sha = ""
    try:
        sha = snapshot_integrity.compute_sha256(p)
    except Exception:
        pass
    symbols: Set[str] = set()
    symbol_to_id: Dict[str, str] = {}
    rows = 0
    with p.open(newline="", encoding="utf-8") as f:
        rdr = csv.DictReader(f)
        fn = rdr.fieldnames or []
        if "symbol" not in fn:
            return set(), {"file": str(p), "sha256": sha, "rows": 0}, {}
        has_id = "instrument_id" in fn
        for row in rdr:
            rows += 1
            sym_val = (row.get("symbol") or "").strip().upper()
            if sym_val:
                symbols.add(sym_val)
            if has_id:
                iid = (row.get("instrument_id") or "").strip()
                if iid and sym_val:
                    symbol_to_id[sym_val] = iid
                aliases = (row.get("aliases") or "").strip()
                for a in aliases.split(";"):
                    a = a.strip().upper()
                    if a and iid:
                        symbol_to_id[a] = iid
                        symbols.add(a)
    return symbols, {"file": str(p), "sha256": sha, "rows": rows}, symbol_to_id


def resolve_symbols(symbols: List[str], symbol_to_id: Dict[str, str]) -> Dict[str, Any]:
    """
    Resolve snapshot symbols to instrument_ids using symbol_to_id (normalized -> instrument_id).
    Returns {instrument_ids: sorted list, alias_map: {symbol: instrument_id}, unknown: sorted list}. Deterministic.
    """
    alias_map: Dict[str, str] = {}
    unknown: List[str] = []
    for s in symbols:
        norm = (s or "").strip().upper()
        if norm in symbol_to_id:
            alias_map[s] = symbol_to_id[norm]
        else:
            unknown.append(s)
    instrument_ids = sorted(set(alias_map.values()))
    return {
        "instrument_ids": instrument_ids,
        "alias_map": dict(sorted(alias_map.items())),
        "unknown": sorted(unknown),
    }
