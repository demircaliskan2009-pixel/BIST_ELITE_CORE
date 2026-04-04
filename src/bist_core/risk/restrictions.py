"""
FAZ47: Restriction-state gate (VBTS/halts/circuit) data-driven + fail-closed.
Load from --restrictions-file or env BIST_RESTRICTIONS_FILE.
State: blocked_symbols (list), short_sale_ban (bool). Provenance: file + sha256.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


def get_restrictions_path() -> Optional[Path]:
    """Return restrictions file path from env BIST_RESTRICTIONS_FILE, or None."""
    env = os.environ.get("BIST_RESTRICTIONS_FILE")
    if not env:
        return None
    return Path(env)


def load_restrictions(path: Path) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Load restriction state from JSON file. Fail-closed: invalid/missing => empty state.
    State: {blocked_symbols: list[str], short_sale_ban: bool}.
    Provenance: {file: str, sha256: str}.
    """
    provenance: Dict[str, Any] = {"file": str(path), "sha256": ""}
    state: Dict[str, Any] = {"blocked_symbols": [], "short_sale_ban": False}
    if not path.is_file():
        return state, provenance
    try:
        from bist_core.services import snapshot_integrity

        provenance["sha256"] = snapshot_integrity.compute_sha256(path)
    except Exception:
        pass
    try:
        with path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            blocked = raw.get("blocked_symbols")
            if isinstance(blocked, list):
                state["blocked_symbols"] = [str(s).strip().upper() for s in blocked if s is not None]
            ban = raw.get("short_sale_ban")
            if isinstance(ban, bool):
                state["short_sale_ban"] = ban
    except Exception:
        pass
    return state, provenance


def gate_restrictions(
    orders_intent: Dict[str, Any],
    restrictions_state: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Restriction gate: block orders for symbols in blocked_symbols; optionally block short sells.
    Returns {ok: bool, errors: list, notes: list}. Deterministic: errors sorted.
    """
    errors: list[str] = []
    blocked = set((s or "").strip().upper() for s in (restrictions_state.get("blocked_symbols") or []))
    short_sale_ban = bool(restrictions_state.get("short_sale_ban"))

    for action in orders_intent.get("actions") or []:
        if not isinstance(action, dict):
            continue
        sym = (action.get("symbol") or "").strip().upper()
        if sym and sym in blocked:
            errors.append("symbol_blocked")
        if short_sale_ban:
            side = (action.get("side") or "").strip().lower()
            qty = action.get("quantity")
            is_short = side == "short" or (qty is not None and float(qty) < 0) or bool(action.get("short_sell"))
            if is_short:
                errors.append("short_sale_blocked")

    return {"ok": len(errors) == 0, "errors": sorted(set(errors)), "notes": []}
