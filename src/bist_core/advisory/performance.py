"""
Performance summary from strategy outcomes.
Deterministic calculations. No network. Fail-closed: missing data => empty report.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

PERFORMANCE_SCHEMA_VERSION = 1


def _default_outcomes_path() -> Path:
    env_path = os.environ.get("BIST_CORE_STRATEGY_OUTCOMES")
    if env_path:
        return Path(env_path)
    from bist_core import config

    return config.REPO_ROOT / "data" / "log" / "strategy_outcomes.jsonl"


def _load_outcomes(path: Path) -> list[dict[str, Any]]:
    """Load outcomes from JSONL. Deterministic order."""
    if not path.is_file():
        return []
    lines = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    out: list[dict[str, Any]] = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _resolved_outcomes(outcomes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Outcomes with r_multiple (win, loss, timeout). Excludes HOLD."""
    return [o for o in outcomes if o.get("status") in ("win", "loss", "timeout") and "r_multiple" in o]


def build_performance_report(
    outcomes_path: Optional[Path] = None,
) -> dict[str, Any]:
    """
    Build performance summary from outcomes JSONL.
    Returns: win_rate, avg_r, total_r, max_dd, trade_count, equity_curve.
    Deterministic. Empty data => zeros and empty curve.
    """
    path = outcomes_path or _default_outcomes_path()
    outcomes = _load_outcomes(path)
    resolved = _resolved_outcomes(outcomes)

    if not resolved:
        return {
            "schema_version": PERFORMANCE_SCHEMA_VERSION,
            "trade_count": 0,
            "win_count": 0,
            "loss_count": 0,
            "win_rate": 0.0,
            "avg_r": 0.0,
            "total_r": 0.0,
            "max_dd": 0.0,
            "equity_curve": [],
        }

    wins = [o for o in resolved if o.get("status") == "win"]
    losses = [o for o in resolved if o.get("status") == "loss"]
    r_values = [float(o["r_multiple"]) for o in resolved]
    win_rate = len(wins) / len(resolved) if resolved else 0.0
    avg_r = sum(r_values) / len(r_values) if r_values else 0.0
    total_r = sum(r_values)

    # Equity curve: sort by exit_day (or day), cumulative R
    def _sort_key(o: dict) -> str:
        return o.get("exit_day") or o.get("day") or ""

    sorted_resolved = sorted(resolved, key=_sort_key)
    cumulative = 0.0
    curve: list[dict[str, Any]] = []
    peak = 0.0
    max_dd = 0.0

    for o in sorted_resolved:
        r = float(o.get("r_multiple", 0.0))
        cumulative += r
        peak = max(peak, cumulative)
        dd = peak - cumulative
        max_dd = max(max_dd, dd)
        curve.append(
            {
                "date": o.get("exit_day") or o.get("day") or "",
                "cumulative_r": round(cumulative, 4),
                "trade_r": round(r, 4),
            }
        )

    return {
        "schema_version": PERFORMANCE_SCHEMA_VERSION,
        "trade_count": len(resolved),
        "win_count": len(wins),
        "loss_count": len(losses),
        "win_rate": round(win_rate, 4),
        "avg_r": round(avg_r, 4),
        "total_r": round(total_r, 4),
        "max_dd": round(max_dd, 4),
        "equity_curve": curve,
    }


def write_performance_csv(report: dict[str, Any], out_path: Path) -> None:
    """Write summary stats as CSV. Deterministic."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "metric,value",
        f"trade_count,{report.get('trade_count', 0)}",
        f"win_count,{report.get('win_count', 0)}",
        f"loss_count,{report.get('loss_count', 0)}",
        f"win_rate,{report.get('win_rate', 0.0)}",
        f"avg_r,{report.get('avg_r', 0.0)}",
        f"total_r,{report.get('total_r', 0.0)}",
        f"max_dd,{report.get('max_dd', 0.0)}",
    ]
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_performance_json(report: dict[str, Any], out_path: Path) -> None:
    """Write full report as JSON. Deterministic keys."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
