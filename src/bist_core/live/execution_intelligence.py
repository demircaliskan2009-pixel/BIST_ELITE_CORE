"""Entry quality, execution gating, slippage add-on, fill timing — deterministic."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from bist_core.models.ohlcv import OHLCVBar


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(x)))


def classify_entry_quality(current_price: float, model_entry: float) -> str:
    """
    Compare spot to model entry (from decision).

    - excellent: price materially below model (better buy)
    - good: within ±1%
    - late: above model by >2% but ≤4%
    - chase: above model by >4% (avoid)
    """
    cp = float(current_price)
    me = float(model_entry)
    if me <= 0 or cp <= 0:
        return "good"
    dp = (cp - me) / me * 100.0
    if dp < -1.0:
        return "excellent"
    if -1.0 <= dp <= 1.0:
        return "good"
    if dp > 4.0:
        return "chase"
    if dp > 2.0:
        return "late"
    return "good"


def map_layer_action(base_action: str, entry_quality: str) -> str:
    """Execution layer mapping for enter-like intents."""
    if base_action not in ("enter", "aggressive_enter", "partial_enter"):
        return base_action
    if entry_quality == "chase":
        return "wait_pullback"
    if entry_quality == "excellent":
        return "aggressive_enter"
    if entry_quality in ("good", "late"):
        return "enter"
    return base_action


def slippage_extra_fraction(volatility: float) -> float:
    """Additional slippage fraction vs mid: volatility * 0.1 (capped)."""
    v = max(0.0, min(0.5, float(volatility)))
    base = min(0.05, v * 0.1)
    try:
        sc = float(os.environ.get("BIST_EXEC_SLIP_SCALE", "1.0"))
    except ValueError:
        sc = 1.0
    sc = max(0.65, min(1.35, sc))
    return min(0.07, base * sc)


def fill_probability(volatility: float, entry_quality: str) -> float:
    """Deterministic fill probability in [0,1]."""
    v = max(0.0, min(0.5, float(volatility)))
    p = 0.92 - v * 1.2
    if entry_quality in ("excellent", "good"):
        p += 0.04
    if entry_quality == "chase":
        p -= 0.45
    if entry_quality == "late":
        p -= 0.06
    return _clamp(p, 0.0, 1.0)


def detect_volatility_spike(buffer: List[OHLCVBar], vol_proxy: float) -> bool:
    """True if last bar move >> rolling vol proxy (spike)."""
    if len(buffer) < 2 or vol_proxy <= 0:
        return False
    c0 = float(buffer[-2].close)
    c1 = float(buffer[-1].close)
    if c0 <= 0:
        return False
    ret = abs(c1 - c0) / c0
    return ret > 2.0 * max(0.001, float(vol_proxy))


@dataclass
class ExecutionPlan:
    final_action: str
    exec_action: str
    entry_quality: str
    effective_price: float
    slippage_extra_frac: float
    size_fraction: float
    delay_this_bar: bool
    fill_probability: float
    reason_suffix: str


class ExecutionMetrics:
    """Cumulative execution telemetry (deterministic aggregates)."""

    def __init__(self) -> None:
        self.slippage_samples: List[float] = []
        self.fill_attempts: int = 0
        self.fills_ok: int = 0
        self.delays: int = 0
        self.quality_scores: List[float] = []

    def record_slippage(self, slip_frac: float) -> None:
        self.slippage_samples.append(float(slip_frac))

    def record_fill(self, ok: bool) -> None:
        self.fill_attempts += 1
        if ok:
            self.fills_ok += 1

    def record_delay(self) -> None:
        self.delays += 1

    def record_quality(self, entry_quality: str) -> None:
        m = {"excellent": 1.0, "good": 0.75, "late": 0.45, "chase": 0.0}
        self.quality_scores.append(float(m.get(entry_quality, 0.5)))

    def summary(self) -> dict[str, Any]:
        avg_sl = (
            sum(self.slippage_samples) / len(self.slippage_samples)
            if self.slippage_samples
            else 0.0
        )
        fr = (
            self.fills_ok / self.fill_attempts
            if self.fill_attempts > 0
            else 0.0
        )
        eq = (
            sum(self.quality_scores) / len(self.quality_scores)
            if self.quality_scores
            else 0.0
        )
        return {
            "source": "execution_intelligence",
            "avg_slippage": round(avg_sl, 8),
            "fill_rate": round(fr, 6),
            "execution_quality_score": round(eq, 6),
            "delays": int(self.delays),
            "fill_attempts": int(self.fill_attempts),
            "fills_ok": int(self.fills_ok),
        }


class ExecutionIntelligenceLayer:
    """decision → execution plan → paper broker (partial 50/50 optional)."""

    def __init__(self) -> None:
        self.metrics = ExecutionMetrics()
        self._partial_leg: Dict[str, str] = {}

    def plan(
        self,
        symbol: str,
        decision: dict[str, Any],
        *,
        current_price: float,
        volatility: float,
        buffer: List[OHLCVBar],
        last_regime: str,
        position_qty: float = 0.0,
        risk_snapshot: Optional[Dict[str, Any]] = None,
    ) -> Optional[ExecutionPlan]:
        """Returns None if not handled (caller uses raw decision)."""
        act = str(decision.get("action", "")).strip().lower()
        if act not in (
            "enter",
            "aggressive_enter",
            "partial_enter",
            "wait_pullback",
            "exit",
            "partial_exit",
        ):
            return None

        sym = str(symbol).strip().upper()
        model_entry = float(decision.get("entry") or current_price)
        eq = classify_entry_quality(current_price, model_entry)

        if act in ("exit", "partial_exit"):
            sf = 0.5 if act == "partial_exit" else 1.0
            slip = slippage_extra_fraction(volatility)
            return ExecutionPlan(
                final_action=act,
                exec_action="exit",
                entry_quality=eq,
                effective_price=float(current_price),
                slippage_extra_frac=slip,
                size_fraction=sf,
                delay_this_bar=False,
                fill_probability=1.0,
                reason_suffix="exit",
            )

        mapped = map_layer_action(act, eq)
        spike = detect_volatility_spike(buffer, volatility)
        choppy = (
            last_regime.strip().upper() == "CHOPPY"
            and os.environ.get("BIST_EXEC_CHOPPY_DELAY", "1").strip() == "1"
        )

        fp = fill_probability(volatility, eq)
        try:
            fpm = float(os.environ.get("BIST_EXEC_FILL_PROB_MULT", "1.0"))
        except ValueError:
            fpm = 1.0
        fpm = max(0.70, min(1.15, fpm))
        fp = _clamp(fp * fpm, 0.0, 1.0)
        min_fp = float(os.environ.get("BIST_EXEC_MIN_FILL_PROB", "0.34"))

        delay = False
        if fp < min_fp:
            delay = True
        if spike:
            delay = True
        if choppy and act in ("enter", "aggressive_enter"):
            delay = True

        slip = slippage_extra_fraction(volatility)
        eff = float(current_price) * (1.0 + slip)

        if delay:
            self.metrics.record_delay()
            return ExecutionPlan(
                final_action="wait_pullback",
                exec_action="wait_pullback",
                entry_quality=eq,
                effective_price=float(current_price),
                slippage_extra_frac=0.0,
                size_fraction=0.0,
                delay_this_bar=True,
                fill_probability=fp,
                reason_suffix=f"delay|eq={eq}|fp={fp:.3f}|spike={spike}|choppy={choppy}",
            )

        if mapped == "wait_pullback":
            return ExecutionPlan(
                final_action="wait_pullback",
                exec_action="wait_pullback",
                entry_quality=eq,
                effective_price=float(current_price),
                slippage_extra_frac=0.0,
                size_fraction=0.0,
                delay_this_bar=False,
                fill_probability=fp,
                reason_suffix=f"eq={eq}|chase",
            )

        size_f = 1.0
        if os.environ.get("BIST_EXEC_PARTIAL", "1").strip() == "1":
            leg = self._partial_leg.get(sym, "a")
            if leg == "a":
                size_f = 0.5
                self._partial_leg[sym] = "b"
            else:
                size_f = 0.5
                self._partial_leg[sym] = "a"

        exec_act = "enter" if mapped in ("enter", "aggressive_enter") else mapped

        risk_sz = 1.0
        rs = risk_snapshot
        if rs:
            try:
                risk_sz = float(rs.get("combined_position_factor", 1.0) or 1.0)
            except (TypeError, ValueError):
                risk_sz = 1.0
            risk_sz = max(0.0, min(1.5, risk_sz))
        size_f = max(0.01, min(1.0, size_f * risk_sz))

        return ExecutionPlan(
            final_action=mapped,
            exec_action=exec_act,
            entry_quality=eq,
            effective_price=eff,
            slippage_extra_frac=slip,
            size_fraction=size_f,
            delay_this_bar=False,
            fill_probability=fp,
            reason_suffix=f"eq={eq}|fp={fp:.3f}|risk_sz={risk_sz:.3f}",
        )

def execution_intel_enabled() -> bool:
    return os.environ.get("BIST_EXEC_INTEL", "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


__all__ = [
    "ExecutionIntelligenceLayer",
    "ExecutionMetrics",
    "ExecutionPlan",
    "classify_entry_quality",
    "execution_intel_enabled",
    "fill_probability",
    "map_layer_action",
    "slippage_extra_fraction",
]
