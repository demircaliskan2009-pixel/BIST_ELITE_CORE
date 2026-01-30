"""Instrument master gate: load CSV (symbol col required) -> symbols set + meta {file, sha256, rows}. Uppercase/strip."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, Set, Tuple

from bist_core.services import snapshot_integrity


def load_instrument_master(path: Path | str) -> Tuple[Set[str], Dict[str, Any]]:
    """
    Load CSV with required 'symbol' column. Returns (symbols_set, meta).
    symbols_set: set of symbol strings, uppercase and stripped.
    meta: {"file": str, "sha256": str, "rows": int}.
    """
    p = Path(path)
    if not p.is_file():
        return set(), {"file": str(p), "sha256": "", "rows": 0}
    sha = ""
    try:
        sha = snapshot_integrity.compute_sha256(p)
    except Exception:
        pass
    symbols: Set[str] = set()
    rows = 0
    with p.open(newline="", encoding="utf-8") as f:
        rdr = csv.DictReader(f)
        if not rdr.fieldnames or "symbol" not in rdr.fieldnames:
            return set(), {"file": str(p), "sha256": sha, "rows": 0}
        for row in rdr:
            rows += 1
            val = (row.get("symbol") or "").strip().upper()
            if val:
                symbols.add(val)
    return symbols, {"file": str(p), "sha256": sha, "rows": rows}
