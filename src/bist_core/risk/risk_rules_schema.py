"""Risk rules schema: load and validate JSON/YAML rules (position limits, max notional, max names, per-symbol cap)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _load_payload(path: Path) -> Dict[str, Any]:
    """Load JSON or YAML from path. Prefer JSON; support YAML if pyyaml available."""
    raw = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix in (".yaml", ".yml"):
        try:
            import yaml

            return yaml.safe_load(raw) or {}
        except ImportError:
            raise ValueError("YAML support requires PyYAML; use .json or install pyyaml")
    return json.loads(raw)


def load_risk_rules(path: Path | str | None) -> Tuple[Dict[str, Any] | None, List[str]]:
    """
    Load risk rules from file. Path from env BIST_CORE_RISK_RULES when path is None.
    Returns (rules_dict, errors). If path is None and env unset, (None, []) = no risk check.
    If path set but file missing or invalid, errors list is non-empty (fail-closed).
    """
    if path is None:
        import os

        path = os.getenv("BIST_CORE_RISK_RULES")
    if not path:
        return None, []
    p = Path(path)
    if not p.is_file():
        return None, ["risk_rules_file_missing"]
    errors: List[str] = []
    try:
        payload = _load_payload(p)
    except Exception as e:
        return None, [f"risk_rules_load_error:{type(e).__name__}"]
    errors = validate_risk_rules(payload)
    if errors:
        return None, errors
    return payload, []


def validate_risk_rules(payload: Dict[str, Any]) -> List[str]:
    """
    Validate risk rules schema. Returns list of error codes (empty if valid).
    Schema: schema_version, optional max_positions, max_notional, max_names, per_symbol_cap.
    """
    errors: List[str] = []
    if not isinstance(payload, dict):
        return ["risk_rules_not_dict"]
    if payload.get("schema_version") != 1:
        errors.append("risk_rules_schema_version")
    max_positions = payload.get("max_positions")
    if max_positions is not None and not isinstance(max_positions, int):
        errors.append("risk_rules_max_positions_invalid")
    elif isinstance(max_positions, int) and max_positions < 0:
        errors.append("risk_rules_max_positions_negative")
    max_notional = payload.get("max_notional")
    if max_notional is not None and not isinstance(max_notional, (int, float)):
        errors.append("risk_rules_max_notional_invalid")
    elif isinstance(max_notional, (int, float)) and max_notional < 0:
        errors.append("risk_rules_max_notional_negative")
    max_names = payload.get("max_names")
    if max_names is not None and not isinstance(max_names, int):
        errors.append("risk_rules_max_names_invalid")
    elif isinstance(max_names, int) and max_names < 0:
        errors.append("risk_rules_max_names_negative")
    per_symbol_cap = payload.get("per_symbol_cap")
    if per_symbol_cap is not None and not isinstance(per_symbol_cap, (int, float)):
        errors.append("risk_rules_per_symbol_cap_invalid")
    elif isinstance(per_symbol_cap, (int, float)) and per_symbol_cap < 0:
        errors.append("risk_rules_per_symbol_cap_negative")
    return errors
