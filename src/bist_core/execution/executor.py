"""Paper executor — simulates execution of trade decisions."""

from __future__ import annotations

from .position import Position

RISK_PER_TRADE = 0.01


def _safe_float(d: dict, key: str) -> float | None:
    v = d.get(key)
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def compute_risk_size(capital: float, entry: float, stop: float) -> float:
    """Position size: capital * risk_per_trade / abs(entry - stop). Deterministic."""
    risk_dist = abs(entry - stop)
    if risk_dist <= 0 or capital <= 0:
        return 0.0
    return capital * RISK_PER_TRADE / risk_dist


class PaperExecutor:
    """Executes decisions in paper mode. Only BUY creates position."""

    def __init__(self, capital: float | None = None) -> None:
        self._capital = capital

    def execute(self, decision: dict, capital: float | None = None) -> dict:
        """Execute decision. BUY creates position; NO_TRADE does nothing.

        If capital provided (ctor or arg), size = capital * 0.01 / abs(entry - stop).
        Else uses decision.size or 1.0.

        Returns:
            {"executed": bool, "position": Position | None, "action": str}
        """
        action = decision.get("action", "")
        if action != "BUY":
            return {"executed": False, "position": None, "action": str(action)}

        symbol = decision.get("symbol")
        entry = _safe_float(decision, "entry")
        stop = _safe_float(decision, "stop")
        target = _safe_float(decision, "target")
        if symbol is None or entry is None or stop is None or target is None:
            return {"executed": False, "position": None, "action": "BUY"}

        cap = capital if capital is not None else self._capital
        size_modifier = _safe_float(decision, "size_modifier") or 1.0
        if cap is not None and cap > 0:
            size = compute_risk_size(cap, entry, stop) * size_modifier
            if size <= 0:
                return {"executed": False, "position": None, "action": "BUY"}
        else:
            size = (_safe_float(decision, "size") or 1.0) * size_modifier

        position = Position(symbol=str(symbol), entry=entry, stop=stop, target=target, size=size)
        result = {"ok": True, "position": position, "action": "BUY"}
        print({"EXECUTION_RESULT": result})
        return result


__all__ = ["PaperExecutor", "compute_risk_size"]
