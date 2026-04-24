"""Trade-level risk and fail-closed gating engine — PRD §9.

Evaluates individual advisor decision objects against a RiskProfile,
enforces fail-closed NO_TRADE on any violation, and computes
capital-aware position sizing.  Deterministic, no network.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List

# ---------------------------------------------------------------------------
# Risk profile
# ---------------------------------------------------------------------------

@dataclass
class RiskProfile:
    capital: float = 100_000.0
    max_risk_per_trade_pct: float = 2.0
    max_daily_loss_pct: float = 5.0
    max_open_positions: int = 10
    min_reward_risk_ratio: float = 1.5


_DEFAULT_PROFILE = RiskProfile()


# ---------------------------------------------------------------------------
# Risk gate result
# ---------------------------------------------------------------------------

@dataclass
class RiskGateResult:
    approved: bool
    reason: str
    position_size: int
    violations: list[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "approved": self.approved,
            "reason": self.reason,
            "position_size": self.position_size,
            "violations": list(self.violations),
        }


# ---------------------------------------------------------------------------
# Capital-aware sizing
# ---------------------------------------------------------------------------

def compute_position_size(
    capital: float,
    entry: float,
    stop: float,
    max_risk_pct: float,
) -> int:
    if capital <= 0 or entry <= 0 or stop <= 0:
        return 0
    stop_distance = abs(entry - stop)
    if stop_distance <= 0:
        return 0
    risk_amount = capital * (max_risk_pct / 100.0)
    size = risk_amount / stop_distance
    return max(int(math.floor(size)), 0)


# ---------------------------------------------------------------------------
# Trade risk gate
# ---------------------------------------------------------------------------

class TradeRiskGate:
    """Evaluate a single decision object against a RiskProfile. Fail-closed."""

    def __init__(
        self,
        profile: RiskProfile | None = None,
    ) -> None:
        self._profile = profile or _DEFAULT_PROFILE
        self._open_position_count: int = 0
        self._daily_loss: float = 0.0

    @property
    def profile(self) -> RiskProfile:
        return self._profile

    @property
    def open_position_count(self) -> int:
        return self._open_position_count

    @property
    def daily_loss(self) -> float:
        return self._daily_loss

    def set_open_positions(self, count: int) -> None:
        self._open_position_count = max(count, 0)

    def record_loss(self, amount: float) -> None:
        if amount > 0:
            self._daily_loss += amount

    def reset_daily(self) -> None:
        self._daily_loss = 0.0

    def evaluate(
        self,
        decision: Dict[str, Any],
    ) -> RiskGateResult:
        violations: list[str] = []

        symbol = str(decision.get("symbol") or "").upper().strip()
        entry = _safe_float(decision.get("entry"))
        stop = _safe_float(decision.get("stop"))
        target = _safe_float(decision.get("target"))
        position_size = _safe_int(decision.get("position_size"))

        if not symbol:
            violations.append("symbol_empty")
        if entry is None or entry <= 0:
            violations.append("entry_invalid")
        if stop is None or stop <= 0:
            violations.append("stop_invalid")
        if target is None or target <= 0:
            violations.append("target_invalid")

        if violations:
            return RiskGateResult(
                approved=False,
                reason="NO_TRADE: " + "; ".join(violations),
                position_size=0,
                violations=violations,
            )

        assert entry is not None and stop is not None and target is not None

        stop_distance = abs(entry - stop)
        if stop_distance <= 0:
            violations.append("stop_distance_zero")
            return RiskGateResult(
                approved=False,
                reason="NO_TRADE: stop_distance_zero",
                position_size=0,
                violations=violations,
            )

        reward = abs(target - entry)
        risk = stop_distance
        rr_ratio = reward / risk if risk > 0 else 0.0
        if rr_ratio < self._profile.min_reward_risk_ratio:
            violations.append(
                f"reward_risk_ratio {rr_ratio:.2f} < min {self._profile.min_reward_risk_ratio:.2f}"
            )

        if position_size is None or position_size <= 0:
            position_size = compute_position_size(
                self._profile.capital,
                entry,
                stop,
                self._profile.max_risk_per_trade_pct,
            )
            if position_size <= 0:
                violations.append("computed_position_size_zero")

        if position_size is not None and position_size > 0:
            risk_amount = stop_distance * position_size
            risk_pct = (risk_amount / self._profile.capital) * 100.0 if self._profile.capital > 0 else float("inf")
            if risk_pct > self._profile.max_risk_per_trade_pct:
                violations.append(
                    f"risk_per_trade {risk_pct:.2f}% > max {self._profile.max_risk_per_trade_pct:.2f}%"
                )

        if self._open_position_count >= self._profile.max_open_positions:
            violations.append(
                f"open_positions {self._open_position_count} >= max {self._profile.max_open_positions}"
            )

        if self._profile.capital > 0:
            daily_loss_pct = (self._daily_loss / self._profile.capital) * 100.0
            if daily_loss_pct >= self._profile.max_daily_loss_pct:
                violations.append(
                    f"daily_loss {daily_loss_pct:.2f}% >= max {self._profile.max_daily_loss_pct:.2f}%"
                )

        if violations:
            return RiskGateResult(
                approved=False,
                reason="NO_TRADE: " + "; ".join(violations),
                position_size=0,
                violations=violations,
            )

        final_size = position_size if position_size is not None and position_size > 0 else 0
        return RiskGateResult(
            approved=True,
            reason="APPROVED",
            position_size=final_size,
            violations=[],
        )

    def evaluate_batch(
        self,
        decisions: List[Dict[str, Any]],
    ) -> List[RiskGateResult]:
        results: list[RiskGateResult] = []
        for d in decisions:
            results.append(self.evaluate(d))
        return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
