"""
FAZ89: Advisory plan — inputs: signals + rules + portfolio snapshot. Output: advisory_plan.json (deterministic).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

ADVISORY_PLAN_SCHEMA_VERSION = 1


def build_advisory_plan(
    signals: List[Dict[str, Any]],
    rules: Dict[str, Any],
    portfolio_snapshot: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Build deterministic advisory plan from signals, rules, portfolio snapshot.
    Returns dict suitable for advisory_plan.json: schema_version, planned_actions (sorted by symbol), rules_summary, portfolio_summary.
    """
    planned = []
    for s in signals:
        if not isinstance(s, dict):
            continue
        sym = (s.get("symbol") or "").strip()
        if not sym:
            continue
        planned.append({
            "symbol": sym,
            "score": round(float(s.get("score", 0)), 6),
            "side": str(s.get("side", "HOLD")).upper() if str(s.get("side", "HOLD")).upper() in ("BUY", "SELL") else "HOLD",
        })
    planned.sort(key=lambda x: x["symbol"])

    rules_summary = dict(sorted((k, v) for k, v in (rules or {}).items() if v is not None))
    pos = portfolio_snapshot.get("positions") or {}
    portfolio_summary = {
        "cash": round(float(portfolio_snapshot.get("cash", 0)), 6),
        "position_count": len(pos),
        "symbols": sorted(pos.keys()),
    }

    return {
        "schema_version": ADVISORY_PLAN_SCHEMA_VERSION,
        "planned_actions": planned,
        "rules_summary": rules_summary,
        "portfolio_summary": portfolio_summary,
    }


def write_advisory_plan(path: Path | str, plan: Dict[str, Any]) -> Path:
    """Write advisory_plan.json with deterministic JSON (sort_keys, indent)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2, sort_keys=True)
    tmp.replace(p)
    return p


__all__ = ["ADVISORY_PLAN_SCHEMA_VERSION", "build_advisory_plan", "write_advisory_plan"]
