"""
FAZ85: Load corporate actions from CSV (path via env/arg); apply to bars using services.adjustments.
Deterministic: sorted actions and bars.
"""

from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def resolve_corporate_actions_path(
    arg_path: str | Path | None, env_key: str = "BIST_CORPORATE_ACTIONS_FILE"
) -> Path | None:
    """Return Path to corporate actions CSV from arg or env; None if neither set or file missing."""
    if arg_path is not None:
        p = Path(arg_path)
        return p if p.is_file() else None
    raw = os.environ.get(env_key)
    if not raw:
        return None
    p = Path(raw)
    return p if p.is_file() else None


def load_actions_from_csv(path: Path | str) -> List[Dict[str, Any]]:
    """
    Load corporate actions from CSV: symbol, effective_date (or ex_date), kind, ratio.
    Returns list of dicts with symbol, effective_date, kind, ratio (float when present). Deterministic sort by (symbol, effective_date, kind).
    """
    p = Path(path)
    rows: List[Dict[str, Any]] = []
    with p.open(newline="", encoding="utf-8") as f:
        rdr = csv.DictReader(f)
        for row in rdr:
            symbol = (row.get("symbol") or "").strip().upper()
            effective_date = (row.get("effective_date") or row.get("ex_date") or "").strip()
            kind = (row.get("kind") or row.get("type") or "").strip()
            ratio_raw = row.get("ratio")
            ratio: Optional[float] = None
            if ratio_raw is not None and str(ratio_raw).strip():
                try:
                    ratio = float(ratio_raw)
                except (TypeError, ValueError):
                    pass
            if symbol and effective_date and kind:
                rec: Dict[str, Any] = {"symbol": symbol, "effective_date": effective_date, "kind": kind}
                if ratio is not None:
                    rec["ratio"] = ratio
                rows.append(rec)
    rows.sort(key=lambda r: (r.get("symbol", ""), r.get("effective_date", ""), r.get("kind", "")))
    return rows


def apply_corporate_actions(
    bars: List[Dict[str, Any]],
    actions: List[Dict[str, Any]],
    *,
    method: str = "backward",
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Apply corporate actions to bars (symbol, date, close). Returns (adjusted_bars, notes). Uses services.adjustments."""
    from bist_core.services.adjustments import apply_close_adjustments

    return apply_close_adjustments(bars, actions, method=method)
