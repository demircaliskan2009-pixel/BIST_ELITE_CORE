"""Discrete edge labels from confidence + directional score — deterministic (no RNG)."""

from __future__ import annotations

import math
from typing import Any, Dict


def compute_edge_signal(
    *,
    confidence: float,
    score: float,
    action: str,
    edge_exp_boost: float | None = None,
) -> str:
    """
    Map continuous confidence / trend score to STRONG_BUY | BUY | SELL | STRONG_SELL | NEUTRAL.

    ``score`` is typically short_trend or brain score in [-1, 1].
    """
    c = max(0.0, min(1.0, float(confidence)))
    s = max(-1.0, min(1.0, float(score)))
    act = str(action).strip().lower()
    print(
        {
            "EDGE_SIGNAL_INPUT": {
                "action": act,
                "confidence": confidence,
                "score": score,
            }
        },
        flush=True,
    )

    if act in ("hold", "wait"):
        if abs(s) < 0.02:
            return "NEUTRAL"
        if s > 0.35:
            return "STRONG_BUY"
        if s > 0.08:
            return "BUY"
        if s < -0.35:
            return "STRONG_SELL"
        if s < -0.08:
            return "SELL"
        return "NEUTRAL"

    if act == "exit":
        return "STRONG_SELL" if c >= 0.45 else "SELL"

    if act in ("enter", "enter_small", "enter_long", "enter_short", "aggressive_enter"):
        eb = float(edge_exp_boost) if edge_exp_boost is not None else None
        amp = math.tanh((eb or 0.0) * 40.0) if eb is not None else 0.0
        adj_s = max(-1.0, min(1.0, s + 0.15 * amp))
        if c >= 0.72 and adj_s > 0.05:
            sig = "STRONG_BUY"
        elif c >= 0.72 and adj_s < -0.05:
            sig = "STRONG_SELL"
        elif c >= 0.45 and adj_s > 0.02:
            sig = "BUY"
        elif c >= 0.45 and adj_s < -0.02:
            sig = "SELL"
        else:
            sig = "BUY" if adj_s >= 0.0 else "SELL"

        # HARD DIRECTION ENFORCEMENT
        if act == "enter_long" and sig in ("SELL", "STRONG_SELL"):
            sig = "BUY"

        if act == "enter_short" and sig in ("BUY", "STRONG_BUY"):
            sig = "SELL"

        print(
            {
                "EDGE_SIGNAL_FINAL": {
                    "action": act,
                    "signal": sig,
                }
            },
            flush=True,
        )

        return sig

    return "NEUTRAL"


def attach_edge_signal_to_decision(d: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure every decision dict exposes string ``edge_signal``."""
    if not isinstance(d, dict):
        return {"edge_signal": "NEUTRAL", "action": "hold", "no_trade": True}
    if d.get("edge_signal") is not None and str(d.get("edge_signal")).strip() != "":
        return d
    conf = float(d.get("confidence") or 0.0)
    try:
        sc = float(d.get("score") or 0.0)
    except (TypeError, ValueError):
        sc = 0.0
    act = str(d.get("action") or "hold")
    eb = d.get("edge_exp_boost")
    try:
        eb_f = float(eb) if eb is not None else None
    except (TypeError, ValueError):
        eb_f = None
    sig = compute_edge_signal(
        confidence=conf,
        score=sc,
        action=act,
        edge_exp_boost=eb_f,
    )
    out = dict(d)
    out["edge_signal"] = sig
    return out


__all__ = ["compute_edge_signal", "attach_edge_signal_to_decision"]
