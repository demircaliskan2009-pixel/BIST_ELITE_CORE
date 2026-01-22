from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


def load_ruleset(path: Path) -> Dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("RulesetNotDict")
    return payload


def validate_ruleset(payload: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    if payload.get("schema_version") != 1:
        errors.append("SchemaVersionMismatch")
    rules = payload.get("rules")
    if not isinstance(rules, list):
        errors.append("RulesNotList")
        return errors
    for idx, rule in enumerate(rules):
        if not isinstance(rule, dict):
            errors.append(f"RuleNotDict:{idx}")
            continue
        if not rule.get("id"):
            errors.append(f"RuleMissingId:{idx}")
        rule_type = rule.get("type")
        if rule_type not in {"max_notional", "trading_disabled"}:
            errors.append(f"RuleUnknownType:{rule.get('id','')}")
        if rule_type == "max_notional":
            max_notional = rule.get("max_notional")
            if not isinstance(max_notional, (int, float)):
                errors.append(f"RuleMaxNotionalInvalid:{rule.get('id','')}")
        if rule_type == "trading_disabled":
            action = rule.get("action", "deny")
            if action not in {"deny"}:
                errors.append(f"RuleTradingActionInvalid:{rule.get('id','')}")
            enabled = rule.get("enabled", True)
            if not isinstance(enabled, bool):
                errors.append(f"RuleTradingEnabledInvalid:{rule.get('id','')}")
            reason = rule.get("reason")
            if reason is not None and not isinstance(reason, str):
                errors.append(f"RuleTradingReasonInvalid:{rule.get('id','')}")
    return errors


def normalize_ruleset(payload: Dict[str, Any]) -> Dict[str, Any]:
    rules = payload.get("rules", [])
    if isinstance(rules, list):
        rules_sorted = sorted(
            [r for r in rules if isinstance(r, dict)],
            key=lambda r: str(r.get("id", "")),
        )
    else:
        rules_sorted = []
    return {
        "schema_version": 1,
        "is_example": bool(payload.get("is_example", False)),
        "rules": rules_sorted,
    }
