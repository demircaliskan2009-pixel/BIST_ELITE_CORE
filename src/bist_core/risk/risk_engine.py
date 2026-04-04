"""Risk engine: validate orders_intent against loaded risk rules (position limits, max notional, max names, per-symbol cap)."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple


def validate_orders_intent(
    orders_intent: Dict[str, Any],
    risk_rules: Dict[str, Any],
) -> Tuple[bool, List[str]]:
    """
    Validate orders_intent against risk rules. Returns (allowed, notes).
    Fail-closed: invalid intent or missing fields => (False, notes).
    Rules: max_positions, max_notional, max_names, per_symbol_cap (all optional).
    """
    notes: List[str] = []
    actions = orders_intent.get("actions")
    if not isinstance(actions, list):
        return False, ["risk_intent_actions_invalid"]

    # Position limits: max number of actions
    max_positions = risk_rules.get("max_positions")
    if isinstance(max_positions, int) and len(actions) > max_positions:
        notes.append("risk_max_positions_exceeded")
        return False, notes

    # Max names: max distinct symbols
    symbols = [a.get("symbol") for a in actions if isinstance(a, dict) and a.get("symbol")]
    unique = len(set(symbols))
    max_names = risk_rules.get("max_names")
    if isinstance(max_names, int) and unique > max_names:
        notes.append("risk_max_names_exceeded")
        return False, notes

    # Per-symbol cap: max weight (or notional proxy) per symbol
    per_symbol_cap = risk_rules.get("per_symbol_cap")
    if isinstance(per_symbol_cap, (int, float)):
        from collections import defaultdict

        weight_by_symbol: Dict[str, float] = defaultdict(float)
        for a in actions:
            if not isinstance(a, dict):
                continue
            sym = a.get("symbol")
            w = a.get("weight")
            if sym is not None and isinstance(w, (int, float)):
                weight_by_symbol[str(sym)] += float(w)
        for sym, w in weight_by_symbol.items():
            if w > float(per_symbol_cap):
                notes.append("risk_per_symbol_cap_exceeded")
                return False, notes

    # Max notional: total weight sum (portfolio proxy when no prices)
    max_notional = risk_rules.get("max_notional")
    if isinstance(max_notional, (int, float)):
        total = 0.0
        for a in actions:
            if isinstance(a, dict):
                w = a.get("weight")
                if isinstance(w, (int, float)):
                    total += float(w)
        if total > float(max_notional):
            notes.append("risk_max_notional_exceeded")
            return False, notes

    return True, notes


# ---------------------------------------------------------------------------
# Trade Risk Engine — position-level risk validation
# ---------------------------------------------------------------------------

RISK_PER_TRADE = 0.015
MAX_POSITIONS = 10
DAILY_LOSS_LIMIT = 0.05


class TradeRiskEngine:
    """Validate positions against risk limits. Fail-closed, deterministic."""

    def __init__(
        self,
        risk_per_trade: float = RISK_PER_TRADE,
        max_positions: int = MAX_POSITIONS,
        daily_loss_limit: float = DAILY_LOSS_LIMIT,
    ) -> None:
        self._risk_per_trade = risk_per_trade
        self._max_positions = max_positions
        self._daily_loss_limit = daily_loss_limit

    def accept(
        self,
        position: dict,
        capital: float,
        cumulative_risk: float,
    ) -> bool:
        """Return True if position passes risk checks."""
        size = position.get("size")
        if size is None:
            return False
        try:
            s = float(size)
        except (TypeError, ValueError):
            return False
        if s <= 0 or not math.isfinite(s):
            return False

        risk_pct = position.get("risk_pct")
        if risk_pct is not None:
            try:
                r = float(risk_pct)
            except (TypeError, ValueError):
                return False
            risk_amount = capital * r
        else:
            entry = position.get("entry")
            stop = position.get("stop")
            if entry is None or stop is None:
                return False
            try:
                e, st = float(entry), float(stop)
            except (TypeError, ValueError):
                return False
            risk_amount = s * (e - st) if e > st else 0.0

        new_total = cumulative_risk + risk_amount
        if capital <= 0:
            return False
        if new_total > capital * self._daily_loss_limit:
            return False
        return True
