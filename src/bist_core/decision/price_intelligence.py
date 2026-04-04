"""Real-time price vs model entry — Matriks/ideal context (deterministic, no RNG)."""

from __future__ import annotations

import math
from typing import Any, Dict, Optional, Tuple


def _finite(x: Any) -> bool:
    try:
        return math.isfinite(float(x))
    except (TypeError, ValueError):
        return False


def compute_entry_quality(current: float, entry: float) -> str:
    """optimal | late | early per ±1% / ±2% bands."""
    if not _finite(current) or not _finite(entry) or entry <= 0:
        return "optimal"
    rel = (float(current) - float(entry)) / float(entry)
    if abs(rel) <= 0.01:
        return "optimal"
    if rel > 0.02:
        return "late"
    if rel < -0.02:
        return "early"
    return "optimal"


def apply_realtime_price_intelligence(
    decision: Dict[str, Any],
    context: Dict[str, Any],
    inst: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], bool]:
    """
    Adjust enter/exit for live price vs model entry; set entry_quality, price_source, validation_diff.

    Returns (decision, price_adjusted_flag).
    """
    out = dict(decision)
    adjusted = False

    current = context.get("current_price")
    if not isinstance(current, (int, float)) or not _finite(current):
        current = out.get("entry", 0.0)
    current_f = float(current)

    price_source = str(context.get("price_source", "ideal"))
    try:
        vd = float(context.get("validation_diff", 0.0))
    except (TypeError, ValueError):
        vd = 0.0
    out["price_source"] = price_source
    out["validation_diff"] = float(vd)

    entry_px = out.get("entry")
    if not isinstance(entry_px, (int, float)) or not _finite(entry_px):
        ideal = context.get("ideal_price")
        if isinstance(ideal, (int, float)) and _finite(ideal):
            entry_px = float(ideal)
        else:
            entry_px = current_f
    entry_f = float(entry_px)

    eq = compute_entry_quality(current_f, entry_f)
    out["entry_quality"] = eq

    if not out.get("institutional"):
        out["price_intelligence_adjusted"] = False
        return out, False

    mom = 0.0
    if inst and isinstance(inst.get("features"), dict):
        try:
            mom = float(inst["features"].get("momentum", 0.0))
        except (TypeError, ValueError):
            mom = 0.0
    elif _finite(out.get("brain_momentum")):
        mom = float(out["brain_momentum"])

    action = str(out.get("action", "hold"))
    reason = str(out.get("reason", ""))

    # --- enter path ---
    if action == "enter":
        if current_f > entry_f * 1.02:
            out["action"] = "wait_pullback"
            out["no_trade"] = True
            out["reason"] = reason + " | entry_missed"
            adjusted = True
        elif current_f < entry_f * 0.98:
            out["action"] = "aggressive_enter"
            out["confidence"] = _clamp01(
                float(out.get("confidence", 0.0)) + 0.05
                if _finite(out.get("confidence"))
                else 0.05
            )
            out["reason"] = reason + " | price_below_model"
            adjusted = True

    # --- anti-blind (late + low confidence) ---
    action = str(out.get("action", "hold"))
    conf = (
        float(out.get("confidence", 0.0)) if _finite(out.get("confidence")) else 0.0
    )
    if action == "enter" and eq == "late" and conf < 0.6:
        out["action"] = "wait_pullback"
        out["no_trade"] = True
        out["reason"] = str(out.get("reason", "")) + " | anti_blind_late"
        adjusted = True

    # --- exit → partial if momentum still positive ---
    action = str(out.get("action", "hold"))
    if action == "exit" and mom > 0.0:
        out["action"] = "partial_exit"
        out["reason"] = str(out.get("reason", "")) + " | momentum_positive"
        adjusted = True

    out["price_intelligence_adjusted"] = adjusted
    return out, adjusted


def _clamp01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return float(x)


__all__ = [
    "apply_realtime_price_intelligence",
    "compute_entry_quality",
]
