"""
FAZ45: Data-driven BIST RulesPack (tick size + price bands) with provenance.
Load from folder: env BIST_RULESPACK_DIR or default data/bist_rules.
tick_sizes.csv: min_price, max_price, tick. price_bands.csv: band_pct (+ optional market).
Evaluators: validate_tick(price, tick), validate_band(ref_price, price, band_pct).
Deterministic: rows sorted by (min_price, band_pct) for stable lookup.
"""
from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Default rulespack dir: env or repo data/bist_rules (lazy to avoid import cycle at module load)
def _default_rulespack_dir() -> Path:
    env = os.environ.get("BIST_RULESPACK_DIR")
    if env:
        return Path(env)
    from bist_core import config
    return config.REPO_ROOT / "data" / "bist_rules"


def get_rulespack_dir() -> Path:
    """Return rulespack folder path (BIST_RULESPACK_DIR or default data/bist_rules)."""
    return _default_rulespack_dir()


def _load_tick_sizes(path: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Read tick_sizes.csv: min_price, max_price, tick. Returns (rows, provenance)."""
    rows: List[Dict[str, Any]] = []
    prov: Dict[str, Any] = {"path": str(path), "source": "tick_sizes.csv", "rows": 0}
    if not path.is_file():
        return rows, prov
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                min_p = float(row.get("min_price", 0))
                max_p = float(row.get("max_price", 0))
                tick = float(row.get("tick", 0))
                if tick > 0:
                    rows.append({"min_price": min_p, "max_price": max_p, "tick": tick})
            except (TypeError, ValueError):
                continue
    rows.sort(key=lambda r: (r["min_price"], r["max_price"]))
    prov["rows"] = len(rows)
    return rows, prov


def _load_price_bands(path: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Read price_bands.csv: band_pct (or min_pct/max_pct) + optional market. Returns (rows, provenance)."""
    rows: List[Dict[str, Any]] = []
    prov: Dict[str, Any] = {"path": str(path), "source": "price_bands.csv", "rows": 0}
    if not path.is_file():
        return rows, prov
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                band_pct = row.get("band_pct")
                if band_pct is not None and band_pct != "":
                    pct = float(band_pct)
                else:
                    min_pct = row.get("min_pct")
                    max_pct = row.get("max_pct")
                    if min_pct is not None and max_pct is not None:
                        pct = (abs(float(min_pct)) + abs(float(max_pct))) / 2.0
                    else:
                        continue
                market = (row.get("market") or "").strip() or None
                rows.append({"band_pct": pct, "market": market})
            except (TypeError, ValueError):
                continue
    rows.sort(key=lambda r: (r["band_pct"], r["market"] or ""))
    prov["rows"] = len(rows)
    return rows, prov


def load_rulespack(rulespack_dir: Optional[Path] = None) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Load RulesPack from folder. Returns (pack, provenance).
    pack: {"tick_sizes": [...], "price_bands": [...], "provenance": {...}}
    provenance: {"dir": str, "tick_sizes": {...}, "price_bands": {...}}
    """
    dir_path = Path(rulespack_dir) if rulespack_dir is not None else _default_rulespack_dir()
    prov: Dict[str, Any] = {"dir": str(dir_path)}
    tick_rows, tick_prov = _load_tick_sizes(dir_path / "tick_sizes.csv")
    band_rows, band_prov = _load_price_bands(dir_path / "price_bands.csv")
    prov["tick_sizes"] = tick_prov
    prov["price_bands"] = band_prov
    pack: Dict[str, Any] = {
        "tick_sizes": tick_rows,
        "price_bands": band_rows,
        "provenance": prov,
    }
    return pack, prov


def tick_for_price(pack: Dict[str, Any], price: float) -> Optional[float]:
    """Return tick for first matching band min_price <= price <= max_price, else None."""
    for row in pack.get("tick_sizes", []):
        if row["min_price"] <= price <= row["max_price"]:
            return row["tick"]
    return None


def band_pct_for_market(pack: Dict[str, Any], market: Optional[str] = None) -> Optional[float]:
    """Return band_pct for market. When market is None, use row with empty market; else match market."""
    bands = pack.get("price_bands", [])
    if not bands:
        return None
    if market:
        for row in bands:
            if (row.get("market") or "").strip() == market:
                return row["band_pct"]
    for row in bands:
        if not (row.get("market") or "").strip():
            return row["band_pct"]
    return bands[0]["band_pct"]


def validate_tick(price: float, tick: float) -> bool:
    """
    True iff price is on tick (round(price/tick)*tick equals price within 1e-9).
    tick must be > 0.
    """
    if tick <= 0:
        return False
    rounded = round(round(price / tick) * tick, 10)
    return abs(rounded - price) <= 1e-9


def validate_band(ref_price: float, price: float, band_pct: float) -> bool:
    """
    True iff price is within band around ref_price: ref*(1 - band_pct/100) <= price <= ref*(1 + band_pct/100).
    ref_price must be > 0; band_pct >= 0.
    """
    if ref_price <= 0 or band_pct < 0:
        return False
    lo = ref_price * (1.0 - band_pct / 100.0)
    hi = ref_price * (1.0 + band_pct / 100.0)
    return lo <= price <= hi


def validate_price_tick(pack: Dict[str, Any], price: float) -> Tuple[bool, Optional[float]]:
    """Return (valid, tick_used). tick_used is None if no band matches."""
    tick = tick_for_price(pack, price)
    if tick is None:
        return False, None
    return validate_tick(price, tick), tick


def validate_price_band(pack: Dict[str, Any], ref_price: float, price: float, market: Optional[str] = None) -> Tuple[bool, Optional[float]]:
    """Return (valid, band_pct_used). band_pct_used is None if no band defined."""
    band_pct = band_pct_for_market(pack, market)
    if band_pct is None:
        return True, None  # no band => pass
    return validate_band(ref_price, price, band_pct), band_pct
