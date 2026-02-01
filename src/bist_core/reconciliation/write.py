"""
FAZ77: Reconciliation stage — compare intended actions vs broker acknowledgements/fills.
Produce deterministic outdir/<day>/reconciliation.json. Stable JSON ordering.
No external libs.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from bist_core.services import snapshot_integrity

RECONCILIATION_SCHEMA_VERSION = 1
RECONCILIATION_FILENAME = "reconciliation.json"


def _symbol_from_action(a: Any) -> str:
    """Normalize symbol from action dict."""
    s = (a.get("symbol") or "").strip()
    return s.upper() if s else ""


def _symbol_from_fill(f: Any) -> str:
    """Normalize symbol from fill dict."""
    s = (f.get("symbol") or "").strip()
    return s.upper() if s else ""


def build_reconciliation_payload(
    day: str,
    actions: List[Dict[str, Any]],
    fills: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Compare intended actions vs fills by symbol. Deterministic: sorted lists.
    Returns dict: schema_version, day, intended_count, fills_count, matched (symbols), unmatched_actions, unmatched_fills, status.
    """
    intended_symbols = sorted(set(_symbol_from_action(a) for a in actions if _symbol_from_action(a)))
    fill_symbols = sorted(set(_symbol_from_fill(f) for f in fills if _symbol_from_fill(f)))
    matched = sorted(set(intended_symbols) & set(fill_symbols))
    unmatched_actions = sorted(set(intended_symbols) - set(fill_symbols))
    unmatched_fills = sorted(set(fill_symbols) - set(intended_symbols))
    status = "ok" if not unmatched_actions and not unmatched_fills else "mismatch"
    return {
        "schema_version": RECONCILIATION_SCHEMA_VERSION,
        "day": str(day),
        "intended_count": len(actions),
        "fills_count": len(fills),
        "matched": matched,
        "unmatched_actions": unmatched_actions,
        "unmatched_fills": unmatched_fills,
        "status": status,
    }


def write_reconciliation(
    outdir: Path | str,
    day: str,
    orders_intent_path: Path | str,
    fills_path: Path | str,
) -> Path:
    """
    Read orders_intent (actions) and fills from fills_path; compare; write outdir/<day>/reconciliation.json.
    Returns path to written file. Deterministic payload.
    """
    out_path = Path(outdir)
    day_str = str(day)
    intent_path = Path(orders_intent_path)
    fills_file = Path(fills_path)
    actions: List[Dict[str, Any]] = []
    if intent_path.is_file():
        try:
            orders_intent = json.loads(intent_path.read_text(encoding="utf-8"))
            actions = orders_intent.get("actions") or []
        except (json.JSONDecodeError, TypeError, OSError):
            actions = []
    fills_list: List[Dict[str, Any]] = []
    if fills_file.is_file():
        with fills_file.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    fills_list.append(json.loads(line))
                except (json.JSONDecodeError, TypeError):
                    continue
    payload = build_reconciliation_payload(day_str, actions, fills_list)
    try:
        from bist_core.security.redact import redact_recursive
        payload = redact_recursive(payload)
    except Exception:
        pass
    day_dir = out_path / day_str
    day_dir.mkdir(parents=True, exist_ok=True)
    out_file = day_dir / RECONCILIATION_FILENAME
    snapshot_integrity.atomic_write_json(out_file, payload)
    return out_file


__all__ = ["write_reconciliation", "build_reconciliation_payload", "RECONCILIATION_SCHEMA_VERSION", "RECONCILIATION_FILENAME"]
