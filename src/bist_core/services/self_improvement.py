"""
FAZ63: Self-improvement runner — evaluates strategies/models via walk-forward backtest,
writes outdir/reports/<day>/model_report.json, selects champion deterministically by metrics gates.
No ML training; only selection + report.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from bist_core.services.backtest import walk_forward


def _select_champion(results: List[Dict[str, Any]]) -> Optional[str]:
    """
    Deterministic champion: among gates_passed, sort by mean_return (desc), then worst_max_drawdown (asc), then name (asc).
    Returns candidate name or None if none pass gates.
    """
    passed = [r for r in results if r.get("gates_passed") is True]
    if not passed:
        return None
    passed.sort(
        key=lambda r: (
            -(float(r.get("mean_return") or 0)),
            float(r.get("worst_max_drawdown") or 0),
            str(r.get("name", "")),
        )
    )
    return str(passed[0].get("name", ""))


def run_self_improvement(
    day: str,
    date_from: str,
    date_to: str,
    snapshot_root: Path | str,
    outdir: Path | str,
    candidates: Optional[List[str]] = None,
    *,
    window_days: int = 21,
    step_days: int = 5,
    top_n: int = 10,
    min_trades: Optional[int] = None,
    max_dd: Optional[float] = None,
    strict: bool = False,
) -> Path:
    """
    Run walk-forward backtest for each candidate (strategy name); write model_report.json;
    select champion by metrics gates (min_trades, max_dd) and deterministic tie-break.
    Returns path to written model_report.json.
    """
    root = Path(snapshot_root)
    out_path = Path(outdir)
    day_str = str(day)
    candidate_list = list(candidates) if candidates else ["equal_weight"]
    # Dedupe and sort for deterministic order
    candidate_list = sorted(set(str(c) for c in candidate_list))

    report_dir = out_path / "reports" / day_str
    report_dir.mkdir(parents=True, exist_ok=True)
    runs_dir = report_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)

    results: List[Dict[str, Any]] = []
    for name in candidate_list:
        candidate_outdir = runs_dir / name
        candidate_outdir.mkdir(parents=True, exist_ok=True)
        try:
            run_config = {
                "snapshot_root": str(root),
                "date_from": date_from,
                "date_to": date_to,
                "outdir": str(candidate_outdir),
                "strategy": name,
                "top_n": top_n,
                "window": window_days,
                "step": step_days,
                "min_trades": min_trades,
                "max_dd": max_dd,
                "strict": strict,
            }
            wf_result = walk_forward(run_config)
        except Exception:
            results.append(
                {
                    "name": name,
                    "strategy": name,
                    "gates_passed": False,
                    "mean_return": 0.0,
                    "worst_max_drawdown": 0.0,
                    "total_fills": 0,
                    "error": "run_failed",
                }
            )
            continue
        agg = wf_result.get("aggregate") or {}
        results.append(
            {
                "name": name,
                "strategy": name,
                "gates_passed": bool(agg.get("gates_passed")),
                "mean_return": agg.get("mean_return", 0.0),
                "worst_max_drawdown": agg.get("worst_max_drawdown", 0.0),
                "total_fills": agg.get("total_fills", 0),
                "num_windows": agg.get("num_windows", 0),
            }
        )

    champion = _select_champion(results)
    any_passed = any(r.get("gates_passed") for r in results)

    report = {
        "schema_version": 1,
        "day": day_str,
        "date_from": date_from,
        "date_to": date_to,
        "candidates": results,
        "champion": champion,
        "gates_passed": any_passed,
    }
    report_file = report_dir / "model_report.json"
    tmp = report_file.with_name(report_file.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, sort_keys=True)
    tmp.replace(report_file)
    return report_file
