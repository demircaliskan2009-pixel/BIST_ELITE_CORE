"""Global capital protection: drawdown, vol, exposure, loss streak — deterministic."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from bist_core.live.risk_operational_fsm import OperationalRiskFSM


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(x)))


def _operational_risk_state(
    *,
    kill_switch: bool,
    pause_cycles_remaining: int,
    pause_entries: bool,
    drawdown_pct: float,
) -> str:
    """PRDV3 §19 — deterministic operational state from existing risk signals (no RNG).

    Ordering: structural halt → recovery cooldown → de-risk constraints → active.
    """
    if kill_switch:
        return "PAUSE"
    if pause_cycles_remaining > 0:
        return "RECOVER"
    d = max(0.0, float(drawdown_pct))
    if pause_entries or d > 0.05:
        return "DE_RISK"
    return "ACTIVE"


def regime_factor(regime: str) -> float:
    r = str(regime or "").strip().upper()
    m = {"TRENDING": 1.05, "CHOPPY": 0.88, "CALM": 0.92, "MIXED": 1.0}
    return float(m.get(r, 1.0))


def drawdown_tier_factor(drawdown_pct: float) -> tuple[float, bool]:
    """
    Returns (position_size_multiplier, kill_switch).

    >5%  → reduce 30%  (×0.7)
    >10% → reduce 60%  (×0.4)
    >15% → stop trading
    """
    d = max(0.0, float(drawdown_pct))
    if d > 0.15:
        return 0.0, True
    if d > 0.10:
        return 0.4, False
    if d > 0.05:
        return 0.7, False
    return 1.0, False


def volatility_position_factor(volatility: float) -> float:
    """High realized vol → smaller positions."""
    v = max(0.0, min(0.5, float(volatility)))
    try:
        high = float(os.environ.get("BIST_RISK_VOL_HIGH", "0.05"))
    except ValueError:
        high = 0.05
    if v <= high:
        return 1.0
    extra = v - high
    return max(0.35, 1.0 - extra * 2.5)


def extreme_volatility(volatility: float) -> bool:
    try:
        thr = float(os.environ.get("BIST_RISK_VOL_EXTREME", "0.12"))
    except ValueError:
        thr = 0.12
    return float(volatility) >= thr


@dataclass
class RiskEngine:
    """Tracks equity path, drawdown, streaks, trade stats; produces sizing factors."""

    peak_equity: float = 1.0
    current_equity: float = 1.0
    max_drawdown_pct: float = 0.0
    losing_streak: int = 0
    pause_cycles_remaining: int = 0
    trade_returns: List[float] = field(default_factory=list)
    risk_samples: List[float] = field(default_factory=list)
    closed_trades: int = 0
    wins: int = 0
    fsm: OperationalRiskFSM = field(default_factory=OperationalRiskFSM)

    def sync_from_dict(self, blob: Optional[Dict[str, Any]]) -> None:
        if not blob:
            return
        try:
            self.peak_equity = float(blob.get("peak_equity", self.peak_equity))
        except (TypeError, ValueError):
            pass
        try:
            self.max_drawdown_pct = float(
                blob.get("max_drawdown_pct", self.max_drawdown_pct)
            )
        except (TypeError, ValueError):
            pass
        try:
            self.losing_streak = int(blob.get("losing_streak", self.losing_streak))
        except (TypeError, ValueError):
            pass
        try:
            self.pause_cycles_remaining = int(
                blob.get("pause_cycles_remaining", self.pause_cycles_remaining)
            )
        except (TypeError, ValueError):
            pass
        tr = blob.get("trade_returns")
        if isinstance(tr, list):
            self.trade_returns = [float(x) for x in tr if _finite_float(x)][-200:]
        rs = blob.get("risk_samples")
        if isinstance(rs, list):
            self.risk_samples = [float(x) for x in rs if _finite_float(x)][-200:]
        try:
            self.closed_trades = int(blob.get("closed_trades", self.closed_trades))
        except (TypeError, ValueError):
            pass
        try:
            self.wins = int(blob.get("wins", self.wins))
        except (TypeError, ValueError):
            pass
        fsm_blob = blob.get("risk_fsm") if isinstance(blob, dict) else None
        if isinstance(fsm_blob, dict):
            self.fsm.sync_from_dict(fsm_blob)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "peak_equity": float(self.peak_equity),
            "max_drawdown_pct": float(self.max_drawdown_pct),
            "losing_streak": int(self.losing_streak),
            "pause_cycles_remaining": int(self.pause_cycles_remaining),
            "trade_returns": list(self.trade_returns[-200:]),
            "risk_samples": list(self.risk_samples[-200:]),
            "closed_trades": int(self.closed_trades),
            "wins": int(self.wins),
            "risk_fsm": self.fsm.to_dict(),
        }

    def update_equity(self, equity: float) -> None:
        e = float(equity)
        if e <= 0:
            return
        self.current_equity = e
        if e > self.peak_equity:
            self.peak_equity = e
        dd = 0.0
        if self.peak_equity > 0:
            dd = (self.peak_equity - e) / self.peak_equity
        self.max_drawdown_pct = max(self.max_drawdown_pct, dd)

    def drawdown_pct(self) -> float:
        if self.peak_equity <= 0:
            return 0.0
        return max(0.0, (self.peak_equity - self.current_equity) / self.peak_equity)

    def tick_cycle(self) -> None:
        if self.pause_cycles_remaining > 0:
            self.pause_cycles_remaining -= 1
            if self.pause_cycles_remaining == 0:
                # Cooldown finished — resume (deterministic reset per spec)
                self.losing_streak = 0

    def loss_streak_factor(self) -> float:
        if self.losing_streak >= 3:
            return 0.5
        return 1.0

    def pause_from_loss_streak(self) -> bool:
        """Temporary pause only while cooldown cycles run (set when streak ≥ 5)."""
        return self.pause_cycles_remaining > 0

    def record_closed_trade(self, pnl_fraction: float, risk_applied: float) -> None:
        """Update streaks and performance stats after a closed trade."""
        p = float(pnl_fraction)
        self.closed_trades += 1
        self.trade_returns.append(p)
        if len(self.trade_returns) > 200:
            self.trade_returns = self.trade_returns[-200:]
        self.risk_samples.append(max(0.0, float(risk_applied)))
        if len(self.risk_samples) > 200:
            self.risk_samples = self.risk_samples[-200:]
        if p < 0:
            self.losing_streak += 1
        else:
            self.losing_streak = 0
        if p > 0:
            self.wins += 1
        try:
            n = int(os.environ.get("BIST_RISK_PAUSE_CYCLES", "12"))
        except ValueError:
            n = 12
        n = max(1, min(500, n))
        if self.losing_streak >= 5:
            self.pause_cycles_remaining = max(self.pause_cycles_remaining, n)

    def winrate(self) -> float:
        if self.closed_trades <= 0:
            return 0.0
        return self.wins / float(self.closed_trades)

    def sharpe_proxy(self) -> float:
        xs = self.trade_returns
        if len(xs) < 2:
            return 0.0
        m = sum(xs) / len(xs)
        var = sum((x - m) ** 2 for x in xs) / max(1, len(xs) - 1)
        sd = var**0.5
        if sd < 1e-12:
            return 0.0
        return m / sd

    def avg_risk_per_trade(self) -> float:
        if not self.risk_samples:
            return 0.0
        return sum(self.risk_samples) / len(self.risk_samples)

    def build_snapshot(
        self,
        *,
        volatility: float,
        regime: str,
        vol_spike: bool,
    ) -> Dict[str, Any]:
        dd = self.drawdown_pct()
        dd_fac, kill = drawdown_tier_factor(dd)
        vol_fac = volatility_position_factor(volatility)
        ls_fac = self.loss_streak_factor()
        reg_fac = regime_factor(regime)
        pause_vol = extreme_volatility(volatility) or bool(vol_spike)
        pause_loss = self.pause_from_loss_streak()

        # final_position_size = base * risk_mult * dd * regime (spec)
        risk_mult = ls_fac * vol_fac
        combined = _clamp(
            risk_mult * dd_fac * reg_fac,
            0.0,
            1.5,
        )
        if kill:
            combined = 0.0
        try:
            rcm = float(os.environ.get("BIST_RISK_COMBINED_MULT", "1.0"))
        except ValueError:
            rcm = 1.0
        rcm = max(0.45, min(1.0, rcm))
        if not kill:
            combined = _clamp(combined * rcm, 0.0, 1.5)

        pause_entries = bool(pause_loss or pause_vol or kill)
        op_state = _operational_risk_state(
            kill_switch=bool(kill),
            pause_cycles_remaining=int(self.pause_cycles_remaining),
            pause_entries=pause_entries,
            drawdown_pct=float(dd),
        )
        self.fsm.step(op_state)

        return {
            "operational_state": str(self.fsm.state),
            "fsm_transition_count": int(self.fsm.transition_count),
            "fsm_last_transition": self.fsm.last_transition,
            "fsm_transitions_observed": bool(self.fsm.transition_count > 0),
            "current_equity": float(self.current_equity),
            "peak_equity": float(self.peak_equity),
            "drawdown_pct": round(dd, 8),
            "max_drawdown_pct": round(self.max_drawdown_pct, 8),
            "drawdown_factor": float(dd_fac),
            "risk_multiplier": round(float(risk_mult), 8),
            "regime_factor": float(reg_fac),
            "vol_factor": round(float(vol_fac), 8),
            "loss_streak_factor": float(ls_fac),
            "combined_position_factor": round(float(combined), 8),
            "kill_switch": bool(kill),
            "pause_entries": bool(pause_loss or pause_vol or kill),
            "pause_loss_streak": bool(pause_loss),
            "pause_volatility": bool(pause_vol),
            "losing_streak": int(self.losing_streak),
            "winrate": round(self.winrate(), 6),
            "sharpe_proxy": round(self.sharpe_proxy(), 6),
            "avg_risk_per_trade": round(self.avg_risk_per_trade(), 6),
        }


def _finite_float(x: Any) -> bool:
    try:
        float(x)
        return True
    except (TypeError, ValueError):
        return False


def risk_engine_enabled() -> bool:
    return os.environ.get("BIST_RISK_ENGINE", "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


__all__ = [
    "RiskEngine",
    "drawdown_tier_factor",
    "extreme_volatility",
    "regime_factor",
    "risk_engine_enabled",
    "volatility_position_factor",
]
