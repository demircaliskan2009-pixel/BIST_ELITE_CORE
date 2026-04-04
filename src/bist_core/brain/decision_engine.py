from __future__ import annotations

from typing import Any

ENTRY_TOLERANCE_PCT = 0.02  # within 2% of score entry = valid
ENTRY_MISSED_PCT = 0.05  # price moved >5% past entry = missed
MIN_RR_RATIO = 1.5  # minimum reward/risk ratio


def _entry_status(current_price: float, entry: float, stop: float) -> str:
    """Classify price relative to intended entry. Deterministic."""
    if entry <= 0 or stop <= 0:
        return "invalid"
    rps = entry - stop
    if rps <= 0:
        return "invalid"
    overshoot = (current_price - entry) / entry if entry > 0 else 0.0
    if overshoot > ENTRY_MISSED_PCT:
        return "missed"
    if current_price < stop:
        return "below_stop"
    if current_price < entry:
        return "pullback"
    if abs(current_price - entry) / entry <= ENTRY_TOLERANCE_PCT:
        return "valid"
    return "valid"


def _build_rationale(features: dict[str, float], score: float) -> str:
    """Build data-driven rationale from actual feature values."""
    m = features.get("momentum", 0.0)
    t = features.get("trend", 0.0)
    r = features.get("rsi_signal", 0.0)
    v = features.get("vol_penalty", 0.0)

    parts = []

    if t > 0:
        parts.append(f"trend bullish (EMA/SMA spread={t:.2f})")
    elif t < 0:
        parts.append(f"trend bearish (EMA/SMA spread={t:.2f})")

    if m > 0.3:
        parts.append(f"strong 20-bar momentum={m:.2f}")
    elif m > 0:
        parts.append(f"positive momentum={m:.2f}")
    elif m < -0.3:
        parts.append(f"strong downward momentum={m:.2f}")
    elif m < 0:
        parts.append(f"negative momentum={m:.2f}")

    if r > 0.3:
        parts.append(f"RSI oversold (signal={r:.2f})")
    elif r < -0.3:
        parts.append(f"RSI overbought (signal={r:.2f})")

    if v > 0.6:
        parts.append(f"high volatility penalty={v:.2f}")
    elif v < 0.2:
        parts.append(f"low volatility={v:.2f}")

    parts.append(f"composite_score={score:.4f}")
    return " | ".join(parts) if parts else f"score={score:.4f}"


def _confidence(score: float, entry_status: str, rr_ratio: float) -> float:
    """Compute confidence [0,1] from score, entry status, and risk/reward."""
    base = min(max(score, 0.0), 1.0)
    status_adj = {"valid": 1.0, "pullback": 0.8, "missed": 0.0, "below_stop": 0.0, "invalid": 0.0}.get(
        entry_status, 0.0
    )
    rr_adj = min(rr_ratio / 3.0, 1.0) if rr_ratio > 0 else 0.0
    return round(base * status_adj * 0.6 + rr_adj * 0.4, 4)


def evaluate(
    symbol: str,
    score_result: dict[str, Any],
    current_price: float,
    stop: float,
    target: float,
) -> dict[str, Any]:
    """Evaluate single symbol decision. Fail-closed on invalid inputs."""
    if not score_result or score_result.get("score") is None:
        return {
            "symbol": symbol,
            "action": "skip",
            "confidence": 0.0,
            "reason": "no_score",
            "entry_status": "invalid",
            "score": 0.0,
        }

    score = float(score_result["score"])
    features = score_result.get("features", {})
    entry = score_result.get("entry")
    try:
        entry = float(entry) if entry is not None else float(current_price)
    except (TypeError, ValueError):
        entry = float(current_price)

    if current_price <= 0 or stop <= 0 or target <= 0:
        return {
            "symbol": symbol,
            "action": "skip",
            "confidence": 0.0,
            "reason": "invalid_price_inputs",
            "entry_status": "invalid",
            "score": score,
        }

    rps = current_price - stop
    rr_ratio = (target - current_price) / rps if rps > 0 else 0.0

    if rr_ratio < MIN_RR_RATIO:
        return {
            "symbol": symbol,
            "action": "skip",
            "confidence": 0.0,
            "reason": f"rr_ratio_too_low={rr_ratio:.2f}",
            "entry_status": "invalid",
            "score": score,
        }

    status = _entry_status(current_price, entry, stop)
    confidence = _confidence(score, status, rr_ratio)
    rationale = _build_rationale(features, score)

    if status in ("missed", "below_stop", "invalid"):
        return {
            "symbol": symbol,
            "action": "skip",
            "confidence": 0.0,
            "reason": f"entry_{status}",
            "entry_status": status,
            "score": score,
        }

    if score < 0.25:
        action = "skip"
    elif confidence >= 0.3:
        action = "enter"
    else:
        action = "wait"

    return {
        "symbol": symbol,
        "score": score,
        "action": action,
        "confidence": confidence,
        "reason": rationale,
        "entry_status": status,
        "rr_ratio": round(rr_ratio, 4),
    }


def rank_decisions(decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort enter decisions by confidence desc, then score desc."""
    enters = [d for d in decisions if d.get("action") == "enter"]
    others = [d for d in decisions if d.get("action") != "enter"]
    enters.sort(key=lambda d: (d.get("confidence", 0), d.get("score", 0)), reverse=True)
    return enters + others
    return enters + others
