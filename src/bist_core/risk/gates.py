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
