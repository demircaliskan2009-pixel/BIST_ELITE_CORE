from __future__ import annotations

from typing import Any, Dict, List

from bist_core.policy.rules_schema import normalize_ruleset, validate_ruleset


def explain_order(
    ruleset: Dict[str, Any],
    *,
    symbol: str,
    price: float,
    side: str,
    qty: float,
    day: str,
) -> Dict[str, Any]:
    normalized = normalize_ruleset(ruleset)
    errors = validate_ruleset(normalized)
    if errors:
        return {
            "schema_version": 1,
            "allowed": False,
            "errors": sorted(errors),
            "violations": [],
            "inputs": {
                "symbol": symbol,
                "price": price,
                "side": side,
                "qty": qty,
                "day": day,
            },
        }
    violations: List[Dict[str, Any]] = []
    notional = float(price) * float(qty)
    for rule in normalized["rules"]:
        if rule.get("type") == "max_notional":
            max_notional = float(rule.get("max_notional"))
            rule_side = str(rule.get("side") or "").upper()
            if rule_side and rule_side != str(side).upper():
                continue
            if notional > max_notional:
                violations.append(
                    {
                        "id": rule.get("id"),
                        "type": "max_notional",
                        "message": rule.get("message", "Order notional exceeds max_notional"),
                        "max_notional": max_notional,
                        "notional": notional,
                    }
                )
    return {
        "schema_version": 1,
        "allowed": len(violations) == 0,
        "errors": [],
        "violations": violations,
        "inputs": {
            "symbol": symbol,
            "price": price,
            "side": side,
            "qty": qty,
            "day": day,
        },
    }
