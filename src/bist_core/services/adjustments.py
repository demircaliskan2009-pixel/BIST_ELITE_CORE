from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Tuple


def apply_close_adjustments(
    bars: List[Dict[str, Any]],
    actions: List[Dict[str, Any]],
    *,
    method: str = "backward",
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    notes: List[Dict[str, Any]] = []
    if method != "backward":
        return bars, [{"error_marker": "UnsupportedMethod"}]

    action_map = _build_action_map(actions)
    adjusted: List[Dict[str, Any]] = []
    for bar in sorted(bars, key=lambda b: (b.get("symbol"), b.get("date"))):
        symbol = bar.get("symbol")
        date_val = bar.get("date")
        close_val = bar.get("close")
        if symbol is None or date_val is None or close_val is None:
            adjusted.append(bar)
            continue
        factor, note_list = _factor_for_symbol_date(
            symbol, date_val, action_map
        )
        if note_list:
            notes.extend(note_list)
        if factor is None:
            adjusted.append(bar)
            continue
        new_bar = dict(bar)
        new_bar["close"] = float(close_val) / factor
        adjusted.append(new_bar)
    return adjusted, notes


def _build_action_map(actions: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for action in actions:
        symbol = action.get("symbol")
        if not symbol:
            continue
        grouped.setdefault(symbol, []).append(action)
    for symbol, rows in grouped.items():
        grouped[symbol] = sorted(rows, key=lambda r: (r.get("effective_date"), r.get("kind")))
    return grouped


def _factor_for_symbol_date(
    symbol: str,
    date_val: str,
    action_map: Dict[str, List[Dict[str, Any]]],
) -> Tuple[float | None, List[Dict[str, Any]]]:
    notes: List[Dict[str, Any]] = []
    actions = action_map.get(symbol, [])
    factor = 1.0
    for action in actions:
        effective_date = action.get("effective_date")
        kind = action.get("kind")
        ratio = action.get("ratio")
        if not effective_date or not kind:
            continue
        if _is_after(date_val, effective_date):
            if kind in {"split", "bonus_issue", "rights_issue"} and ratio:
                factor *= float(ratio)
            elif kind == "reverse_split" and ratio:
                factor /= float(ratio)
            elif kind == "cash_dividend":
                notes.append({"symbol": symbol, "note": "cash_dividend_ignored"})
            elif kind in {"symbol_change", "isin_change"}:
                notes.append({"symbol": symbol, "note": f"{kind}_ignored"})
    return factor if factor != 1.0 else None, notes


def _is_after(date_val: str, effective_date: str) -> bool:
    try:
        return datetime.fromisoformat(date_val) < datetime.fromisoformat(effective_date)
    except Exception:
        return False
