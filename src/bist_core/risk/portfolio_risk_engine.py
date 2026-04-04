"""Portfolio-level exposure and drawdown checks (fail-closed)."""

from __future__ import annotations

from typing import Any, List, Tuple


class PortfolioRiskEngine:
    def __init__(self) -> None:
        self.max_total_exposure = 1.0
        self.max_symbol_exposure = 0.25
        self.max_drawdown = 0.15

    def validate(
        self,
        portfolio: List[dict[str, Any]],
        equity: float,
        peak_equity: float,
    ) -> Tuple[bool, str]:
        """Return (True, \"\") or (False, reason_code)."""
        try:
            pe = float(peak_equity)
            eq = float(equity)
        except (TypeError, ValueError):
            return False, "invalid_equity_inputs"

        if pe <= 0:
            return False, "invalid_peak_equity"

        dd = (eq - pe) / pe
        if dd < -float(self.max_drawdown):
            return False, "max_drawdown_breached"

        if not portfolio:
            return True, ""

        total = 0.0
        for p in portfolio:
            try:
                w = float(p.get("weight", 0) or 0.0)
            except (TypeError, ValueError):
                return False, "invalid_weight"
            if w < 0:
                return False, "negative_weight"
            total += w
            if w > float(self.max_symbol_exposure) + 1e-12:
                return False, "max_symbol_exposure_breached"

        if total > float(self.max_total_exposure) + 1e-12:
            return False, "max_total_exposure_breached"

        return True, ""


__all__ = ["PortfolioRiskEngine"]
