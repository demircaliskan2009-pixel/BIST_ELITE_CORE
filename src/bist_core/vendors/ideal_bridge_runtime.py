from __future__ import annotations

import csv
import os
from functools import lru_cache
from pathlib import Path
from typing import Optional


def _bridge_csv_path() -> Path | None:
    env = os.environ.get("BIST_CORE_IDEAL_BRIDGE_CSV")
    if env:
        p = Path(env)
        return p if p.exists() else None

    default_p = Path("artifacts/ideal_bridge_live_v1/bridge_snapshot.csv")
    return default_p if default_p.exists() else None


@lru_cache(maxsize=4)
def _load_bridge_table_cached(path_str: str) -> dict[str, dict]:
    p = Path(path_str)
    out: dict[str, dict] = {}
    with p.open("r", encoding="utf-8", errors="ignore") as f:
        for row in csv.DictReader(f):
            sym = str(row.get("symbol", "")).strip().upper()
            if sym:
                out[sym] = row
    return out


def clear_bridge_runtime_cache() -> None:
    _load_bridge_table_cached.cache_clear()


def get_live_bridge_row(symbol: str) -> Optional[dict]:
    p = _bridge_csv_path()
    if p is None:
        return None
    table = _load_bridge_table_cached(str(p.resolve()))
    return table.get(str(symbol).strip().upper())
