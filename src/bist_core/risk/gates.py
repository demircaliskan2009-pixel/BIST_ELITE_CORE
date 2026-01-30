"""RiskGateEngine: fail-closed gate for execution (stage errors or policy invalid => deny)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional


class RiskGateEngine:
    """Evaluate whether orders_intent is allowed for execution. Fail-closed: default deny if any stage errors >0 or policy invalid."""

    def evaluate(
        self,
        orders_intent: Dict[str, Any],
        *,
        policy_ruleset: Optional[Dict[str, Any]] = None,
        stages: Dict[str, Any],
        rulespack: Optional[Dict[str, Any]] = None,
    ) -> tuple[bool, List[str]]:
        notes: List[str] = []
        if not isinstance(stages, dict):
            notes.append("blocked")
            return False, notes
        for name, stage in stages.items():
            if not isinstance(stage, dict):
                continue
            err = stage.get("errors", 0)
            if err is not None and int(err) > 0:
                notes.append("blocked")
                return False, notes
        if rulespack:
            from bist_core.risk.rulespack import validate_price_tick, validate_price_band
            actions = orders_intent.get("actions") or []
            for a in actions:
                if not isinstance(a, dict):
                    continue
                price = a.get("price")
                if price is None:
                    continue
                try:
                    p = float(price)
                except (TypeError, ValueError):
                    notes.append("rulespack_price_invalid")
                    return False, notes
                ok_tick, _ = validate_price_tick(rulespack, p)
                if not ok_tick:
                    notes.append("rulespack_tick_violation")
                    return False, notes
                ref = a.get("ref_price")
                if ref is not None:
                    try:
                        ref_p = float(ref)
                    except (TypeError, ValueError):
                        continue
                    market = a.get("market")
                    ok_band, _ = validate_price_band(rulespack, ref_p, p, market)
                    if not ok_band:
                        notes.append("rulespack_band_violation")
                        return False, notes
        if policy_ruleset is not None:
            try:
                from bist_core.policy.rules_engine import evaluate as policy_evaluate
                allowed, reasons = policy_evaluate(
                    policy_ruleset,
                    trading_context={"day": orders_intent.get("day", "")},
                )
                if not allowed:
                    notes.append("blocked")
                    notes.extend(reasons)
                    return False, notes
            except Exception:
                notes.append("blocked")
                return False, notes
        return True, notes
