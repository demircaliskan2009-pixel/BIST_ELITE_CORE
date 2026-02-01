"""
FAZ94: Strategy runner — offline bars + signals -> strategy_report.json.
Runs engine.decide(bars, bands, ...); outputs deterministic report (schema_version, day, decisions, summary).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from bist_core.models import EODBar, PriceBand
from bist_core.strategy.engine import decide


STRATEGY_REPORT_SCHEMA_VERSION = 1


def run(
    bars: List[EODBar],
    bands: List[PriceBand],
    strat_cfg: Dict[str, Any],
    *,
    kap_events: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    cfg: Optional[Any] = None,
    gates_cfg: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Run strategy on offline bars; returns strategy report dict (decisions + summary).
    Same bars + same config -> same report (deterministic).
    """
    if not bars:
        return _report_from_decisions([], None)

    symbols = sorted(set(b.symbol for b in bars))
    kap = kap_events if isinstance(kap_events, dict) else {}
    decisions = decide(
        symbols=symbols,
        bars=bars,
        bands=bands,
        kap_events=kap,
        cfg=cfg or {},
        gates_cfg=gates_cfg or {},
        strat_cfg=strat_cfg,
    )
    day = max(b.date for b in bars).isoformat() if bars else None
    return _report_from_decisions(decisions, day)


def _report_from_decisions(
    decisions: List[Dict[str, Any]],
    day: Optional[str],
) -> Dict[str, Any]:
    """Build deterministic report: decisions sorted by symbol; summary counts."""
    sorted_decisions = sorted(decisions, key=lambda d: (d.get("symbol", ""), d.get("date", "")))
    count_buy = sum(1 for d in sorted_decisions if d.get("decision_raw") == "BUY")
    count_watch = sum(1 for d in sorted_decisions if d.get("decision_raw") == "WATCH")
    count_pass = sum(1 for d in sorted_decisions if d.get("decision_raw") == "PASS" or d.get("decision") == "PASS")
    symbols = sorted(set(d.get("symbol", "") for d in sorted_decisions if d.get("symbol")))

    return {
        "schema_version": STRATEGY_REPORT_SCHEMA_VERSION,
        "day": day,
        "decisions": sorted_decisions,
        "summary": {
            "count_buy": count_buy,
            "count_watch": count_watch,
            "count_pass": count_pass,
            "symbols": symbols,
        },
    }


def write_strategy_report(path: Path | str, report: Dict[str, Any]) -> Path:
    """Write strategy_report.json with deterministic key order."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, sort_keys=True)
    tmp.replace(p)
    return p


__all__ = ["run", "write_strategy_report", "STRATEGY_REPORT_SCHEMA_VERSION"]
