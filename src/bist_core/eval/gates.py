"""
FAZ95: Eval gates — metrics -> pass/fail; fail -> exit 2 + artifacts.
Standard gates: min_trades (total_fills >= N), max_dd (max_drawdown <= M).
Deterministic: same metrics + same gates -> same result.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Gate names and how they are checked (metrics key, gate key, pass condition)
# min_trades: metrics["total_fills"] >= gates["min_trades"]
# max_dd: metrics["max_drawdown"] <= gates["max_dd"] (or metrics["worst_max_drawdown"])
GATE_MIN_TRADES = "min_trades"
GATE_MAX_DD = "max_dd"

EVAL_REPORT_SCHEMA_VERSION = 1


def evaluate(metrics: Dict[str, Any], gates: Dict[str, Any]) -> Dict[str, Any]:
    """
    Evaluate metrics against gates. Returns { passed, failed_gates, details }.
    Gates: min_trades (metrics.total_fills >= value), max_dd (metrics.max_drawdown <= value).
    None gate value = gate not applied.
    """
    failed_gates: List[str] = []
    details: Dict[str, Any] = {}

    min_trades = gates.get(GATE_MIN_TRADES)
    if min_trades is not None:
        total_fills = metrics.get("total_fills")
        if total_fills is None:
            total_fills = metrics.get("total_fill_count", 0)
        try:
            total_fills = int(total_fills)
        except (TypeError, ValueError):
            total_fills = 0
        threshold = int(min_trades)
        ok = total_fills >= threshold
        details[GATE_MIN_TRADES] = {"value": total_fills, "threshold": threshold, "passed": ok}
        if not ok:
            failed_gates.append(GATE_MIN_TRADES)

    max_dd_gate = gates.get(GATE_MAX_DD)
    if max_dd_gate is not None:
        max_dd = metrics.get("max_drawdown")
        if max_dd is None:
            max_dd = metrics.get("worst_max_drawdown", 0.0)
        try:
            max_dd = float(max_dd)
        except (TypeError, ValueError):
            max_dd = 0.0
        threshold = float(max_dd_gate)
        ok = max_dd <= threshold
        details[GATE_MAX_DD] = {"value": max_dd, "threshold": threshold, "passed": ok}
        if not ok:
            failed_gates.append(GATE_MAX_DD)

    passed = len(failed_gates) == 0
    return {
        "passed": passed,
        "failed_gates": sorted(failed_gates),
        "details": details,
    }


def run_gates(
    metrics: Dict[str, Any],
    gates: Dict[str, Any],
    *,
    outdir: Optional[Path | str] = None,
    strict: bool = True,
) -> Tuple[bool, int, Dict[str, Any]]:
    """
    Evaluate metrics against gates. On fail and outdir set: write eval_report.json artifact.
    Returns (passed, exit_code, artifacts). fail -> exit_code 2 + artifacts with report path.
    """
    result = evaluate(metrics, gates)
    passed = result["passed"]
    exit_code = 2 if (strict and not passed) else 0
    artifacts: Dict[str, Any] = {}

    if not passed and outdir is not None:
        metrics_snapshot = {}
        for k in ("total_fills", "total_fill_count", "max_drawdown", "worst_max_drawdown", "mean_return"):
            if k in metrics:
                metrics_snapshot[k] = metrics[k]
        report = {
            "schema_version": EVAL_REPORT_SCHEMA_VERSION,
            "passed": False,
            "failed_gates": result["failed_gates"],
            "details": result["details"],
            "metrics": metrics_snapshot,
        }
        out_path = Path(outdir)
        out_path.mkdir(parents=True, exist_ok=True)
        report_path = out_path / "eval_report.json"
        _write_json(report_path, report)
        artifacts["eval_report_path"] = str(report_path)

    return passed, exit_code, artifacts


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    """Atomic write JSON (sort_keys for determinism)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
    tmp.replace(path)


__all__ = ["evaluate", "run_gates", "GATE_MIN_TRADES", "GATE_MAX_DD", "EVAL_REPORT_SCHEMA_VERSION"]
