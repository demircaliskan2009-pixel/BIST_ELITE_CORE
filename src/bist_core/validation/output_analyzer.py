#!/usr/bin/env python3
"""
Parse live_runner capture (validation_run.txt), extract metrics, classify edge, diagnose.

Deterministic — no RNG, no network.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path
from typing import Any


def _try_parse_line(line: str) -> dict[str, Any] | None:
    s = line.strip()
    if not s or not s.startswith("{"):
        return None
    for parser in (json.loads, ast.literal_eval):
        try:
            obj = parser(s)
        except (SyntaxError, ValueError, json.JSONDecodeError):
            continue
        if isinstance(obj, dict):
            return obj
    return None


def parse_validation_file(path: Path) -> dict[str, Any]:
    """Extract last-seen metric blocks and decision action histogram."""
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    last_sim: dict[str, Any] | None = None
    last_mr: dict[str, Any] | None = None
    last_ex: dict[str, Any] | None = None
    last_risk: dict[str, Any] | None = None
    last_status: dict[str, Any] | None = None
    last_risk_status: dict[str, Any] | None = None
    decision_actions: list[str] = []
    line_dicts: list[dict[str, Any]] = []

    for line in lines:
        d = _try_parse_line(line)
        if d is None:
            continue
        line_dicts.append(d)
        if "SIMULATION_SUMMARY" in d:
            last_sim = d["SIMULATION_SUMMARY"]  # type: ignore[assignment]
        if "MARKET_REALISM" in d:
            last_mr = d["MARKET_REALISM"]  # type: ignore[assignment]
        if "EXECUTION_METRICS" in d:
            last_ex = d["EXECUTION_METRICS"]  # type: ignore[assignment]
        if "RISK_METRICS" in d:
            last_risk = d["RISK_METRICS"]  # type: ignore[assignment]
        if "SYSTEM_STATUS_REPORT" in d:
            last_status = d["SYSTEM_STATUS_REPORT"]  # type: ignore[assignment]
        if "RISK_STATUS" in d:
            last_risk_status = d["RISK_STATUS"]  # type: ignore[assignment]
        st = d.get("stage")
        if st == "decision" and isinstance(d.get("action"), str):
            decision_actions.append(str(d["action"]))

    return {
        "SIMULATION_SUMMARY": last_sim,
        "MARKET_REALISM": last_mr,
        "EXECUTION_METRICS": last_ex,
        "RISK_METRICS": last_risk,
        "SYSTEM_STATUS_REPORT": last_status,
        "last_risk_status": last_risk_status,
        "decision_actions": decision_actions,
        "line_count": len(lines),
        "parsed_dict_lines": len(line_dicts),
    }


def _f(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def _i(x: Any, default: int = 0) -> int:
    try:
        return int(x)
    except (TypeError, ValueError):
        return default


def compute_derived(parsed: dict[str, Any]) -> dict[str, Any]:
    sim = parsed.get("SIMULATION_SUMMARY") or {}
    mr = parsed.get("MARKET_REALISM") or {}
    risk = parsed.get("RISK_METRICS") or {}
    actions = parsed.get("decision_actions") or []

    total_cycles = _i(sim.get("total_cycles"), 0)
    actions_gen = _i(sim.get("actions_generated"), 0)
    apc = actions_gen / max(1, total_cycles)

    fill_sr = _f(mr.get("fill_success_rate"), -1.0)
    missed = _i(mr.get("missed_trades"), -1)
    avg_slip = _f(mr.get("avg_slippage_fraction"), -1.0)
    avg_dd = _f(risk.get("max_drawdown"), 0.0)
    winrate = _f(risk.get("winrate"), 0.0)
    sym_ct = len(sim.get("active_symbols") or [])
    turnover = actions_gen / max(1, total_cycles * max(1, sym_ct))

    uniq = sorted(set(actions))
    action_diversity = len(uniq)

    return {
        "actions_per_cycle": round(apc, 8),
        "fill_success_rate": fill_sr,
        "missed_trades": missed,
        "avg_slippage_fraction": avg_slip,
        "avg_drawdown_max": avg_dd,
        "winrate_proxy": winrate,
        "portfolio_turnover_proxy": round(turnover, 8),
        "action_diversity": action_diversity,
        "unique_actions": uniq,
    }


def detect_failures(
    parsed: dict[str, Any], derived: dict[str, Any]
) -> list[str]:
    flags: list[str] = []
    sim = parsed.get("SIMULATION_SUMMARY")
    mr = parsed.get("MARKET_REALISM")
    risk = parsed.get("RISK_METRICS")

    if sim is None:
        flags.append("missing_SIMULATION_SUMMARY")
    if mr is None:
        flags.append("missing_MARKET_REALISM")
    if parsed.get("EXECUTION_METRICS") is None:
        flags.append("missing_EXECUTION_METRICS")
    if risk is None:
        flags.append("missing_RISK_METRICS")
    if parsed.get("SYSTEM_STATUS_REPORT") is None:
        flags.append("missing_SYSTEM_STATUS_REPORT")

    tc = _i((sim or {}).get("total_cycles"), 0)
    if tc < 800:
        flags.append(f"short_run_cycles_{tc}_lt_800")

    fr = derived["fill_success_rate"]
    if fr >= 0 and fr > 0.90:
        flags.append("fill_rate_gt_90_unrealistic")
    if fr >= 0 and fr < 0.30:
        flags.append("fill_rate_lt_30_too_strict")

    slip = derived["avg_slippage_fraction"]
    if slip >= 0 and slip < 1e-8:
        flags.append("slippage_near_zero_suspicious")

    mt = derived["missed_trades"]
    attempts_implied = (sim or {}).get("actions_generated")
    if mr is not None and mt == 0 and _i(attempts_implied, 0) > 5:
        flags.append("missed_trades_zero_suspicious")

    if derived["avg_drawdown_max"] > 0.15:
        flags.append("drawdown_gt_15pct_unstable")

    ag = _i((sim or {}).get("actions_generated"), 0)
    if ag < 20:
        flags.append("actions_generated_lt_20_dead")

    if (
        derived["action_diversity"] <= 1
        and ag > 10
        and len(parsed.get("decision_actions") or []) > 10
    ):
        flags.append("no_action_diversity")

    return flags


def classify_edge(
    parsed: dict[str, Any], derived: dict[str, Any], flags: list[str]
) -> str:
    if "drawdown_gt_15pct_unstable" in flags:
        return "UNSTABLE_SYSTEM"
    if "actions_generated_lt_20_dead" in flags:
        return "UNDER_TRADING_SYSTEM"
    if "short_run_cycles_" in "".join(flags):
        return "INCOMPLETE_RUN"
    if (
        "fill_rate_gt_90_unrealistic" in flags
        or "slippage_near_zero_suspicious" in flags
        or "missed_trades_zero_suspicious" in flags
    ):
        return "FAKE_EDGE"
    if (
        "fill_rate_lt_30_too_strict" in flags
        or "no_action_diversity" in flags
    ):
        return "LOW_SIGNAL_SYSTEM"
    return "REAL_EDGE"


def edge_confidence(
    flags: list[str], derived: dict[str, Any], system_type: str
) -> float:
    base = 0.65
    if "missing_" in "".join(flags):
        base -= 0.25
    if system_type == "REAL_EDGE":
        base += 0.15
        if 0.30 <= derived["fill_success_rate"] <= 0.90:
            base += 0.08
        if derived["missed_trades"] > 0:
            base += 0.05
        if derived["avg_slippage_fraction"] > 1e-6:
            base += 0.05
    if system_type == "FAKE_EDGE":
        base = min(0.55, base)
    if system_type == "UNSTABLE_SYSTEM":
        base = 0.35
    if system_type == "UNDER_TRADING_SYSTEM":
        base = 0.42
    if system_type == "INCOMPLETE_RUN":
        base = 0.25
    if system_type == "LOW_SIGNAL_SYSTEM":
        base = 0.48
    return max(0.0, min(1.0, round(base, 4)))


def main_weakness(flags: list[str], system_type: str) -> str:
    if not flags:
        return "none_detected"
    priority = (
        "missing_SIMULATION_SUMMARY",
        "missing_MARKET_REALISM",
        "missing_EXECUTION_METRICS",
        "missing_RISK_METRICS",
        "missing_SYSTEM_STATUS_REPORT",
        "short_run_cycles",
        "actions_generated_lt_20_dead",
        "drawdown_gt_15pct_unstable",
        "fill_rate_gt_90_unrealistic",
        "fill_rate_lt_30_too_strict",
        "slippage_near_zero_suspicious",
        "missed_trades_zero_suspicious",
        "no_action_diversity",
    )
    for p in priority:
        for f in flags:
            if f.startswith(p) or p in f:
                return f
    return flags[0]


def fix_suggestions(flags: list[str], system_type: str) -> list[str]:
    out: list[str] = []
    if any("fill_rate_gt_90" in f for f in flags):
        out.append(
            "execution: tighten BIST_MIN_FILL_RATIO / liquidity floor in "
            "RealisticExecutionEngine or reduce volume_proxy optimism"
        )
    if any("fill_rate_lt_30" in f for f in flags):
        out.append(
            "execution: relax _MIN_FILL_RATIO / depth_per_unit; "
            "check BIST_EXEC_MIN_FILL_PROB"
        )
    if any("slippage" in f for f in flags):
        out.append(
            "execution: verify volatility proxy and size_fraction scaling; "
            "ensure BIST_EXEC_INTEL slippage path active"
        )
    if any("missed_trades_zero" in f for f in flags):
        out.append(
            "execution: borderline miss threshold in process_fill; "
            "ensure volume_proxy not always infinite"
        )
    if any("drawdown" in f for f in flags):
        out.append(
            "risk: tighten BIST_RISK_* thresholds; reduce BIST_PORTFOLIO_RISK_BUDGET"
        )
    if any("actions_generated_lt_20" in f for f in flags):
        out.append(
            "portfolio/decision: relax BIST_PORTFOLIO_MIN_CONF / BIST_ADAPTIVE_*; "
            "BIST_DECISION_RELAX_MODE for simulation only"
        )
    if any("no_action_diversity" in f for f in flags):
        out.append(
            "decision: verify multi-symbol feed; expand BIST_SYMBOLS; "
            "check relax mode stuck"
        )
    if any("missing_" in f for f in flags):
        out.append(
            "run: ensure live_runner completes; capture full stdout to validation_run.txt"
        )
    if any("short_run" in f for f in flags):
        out.append("run: set BIST_LIVE_MAX_CYCLES>=800 and no early exit")
    if not out:
        out.append("maintain: monitor RISK_METRICS and MARKET_REALISM each release")
    return out


def run_analysis(path: Path, json_output: Path | None = None) -> int:
    if not path.is_file():
        print(json.dumps({"error": "file_not_found", "path": str(path)}))
        return 2

    parsed = parse_validation_file(path)
    derived = compute_derived(parsed)
    flags = detect_failures(parsed, derived)
    system_type = classify_edge(parsed, derived, flags)
    conf = edge_confidence(flags, derived, system_type)
    weakness = main_weakness(flags, system_type)
    fixes = fix_suggestions(flags, system_type)

    diagnosis = {
        "SYSTEM_TYPE": system_type,
        "MAIN_WEAKNESS": weakness,
        "EDGE_CONFIDENCE": conf,
        "NEXT_FIX_PRIORITY": fixes[0] if fixes else "none",
    }

    full_summary = {
        "extracted": {
            "SIMULATION_SUMMARY": parsed.get("SIMULATION_SUMMARY"),
            "MARKET_REALISM": parsed.get("MARKET_REALISM"),
            "EXECUTION_METRICS": parsed.get("EXECUTION_METRICS"),
            "RISK_METRICS": parsed.get("RISK_METRICS"),
            "SYSTEM_STATUS_REPORT": parsed.get("SYSTEM_STATUS_REPORT"),
        },
        "derived_metrics": derived,
        "failure_flags": flags,
        "diagnosis": diagnosis,
        "auto_fix_suggestions": fixes,
    }

    if json_output is not None:
        json_output.parent.mkdir(parents=True, exist_ok=True)
        json_output.write_text(
            json.dumps(full_summary, indent=2, default=str),
            encoding="utf-8",
        )

    print("=== FULL METRICS SUMMARY ===")
    print(json.dumps(full_summary, indent=2, default=str))
    print()
    print("=== EDGE CLASSIFICATION ===")
    print(json.dumps({"SYSTEM_TYPE": system_type}, indent=2))
    print()
    print("=== SYSTEM DIAGNOSIS ===")
    print(json.dumps(diagnosis, indent=2))
    print()
    print("=== NEXT ACTION PLAN ===")
    for i, s in enumerate(fixes, 1):
        print(f"{i}. {s}")
    print()
    print("SYSTEM VALIDATION COMPLETE — TRUTH REVEALED")
    return 0 if not any(f.startswith("missing_") for f in flags) else 1


def main() -> None:
    ap = argparse.ArgumentParser(description="Analyze validation_run.txt capture")
    ap.add_argument(
        "--input",
        type=Path,
        default=Path("validation_run.txt"),
        help="Path to captured live_runner stdout",
    )
    ap.add_argument(
        "--json-output",
        type=Path,
        default=None,
        help="Write full machine-readable summary JSON",
    )
    args = ap.parse_args()
    sys.exit(run_analysis(args.input, args.json_output))


if __name__ == "__main__":
    main()
