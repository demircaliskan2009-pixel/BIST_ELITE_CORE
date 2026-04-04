from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .store import ensure_store, load_recommendations


def _avg(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def build_report(root: str | Path | None = None) -> dict[str, Any]:
    records = load_recommendations(root)
    open_records = [x for x in records if x.status == "open"]
    closed_records = [x for x in records if x.status == "closed"]

    decision_counts = Counter(x.decision for x in records)
    outcome_counts = Counter((x.outcome_label or "unset") for x in closed_records)

    realized_r = [float(x.realized_return_r) for x in closed_records if isinstance(x.realized_return_r, (int, float))]
    realized_pct = [float(x.realized_return_pct) for x in closed_records if isinstance(x.realized_return_pct, (int, float))]

    wins = outcome_counts.get("win", 0)
    losses = outcome_counts.get("loss", 0)
    decided = wins + losses
    win_rate = None if decided == 0 else wins / decided

    latest_created_at = None if not records else max(x.created_at for x in records)
    latest_closed_candidates = [x.closed_at for x in closed_records if x.closed_at]
    latest_closed_at = None if not latest_closed_candidates else max(latest_closed_candidates)
    latest_day = None if not records else max(x.day for x in records)

    grouped: dict[str, list] = defaultdict(list)
    for rec in records:
        grouped[rec.symbol].append(rec)

    symbols: list[dict[str, Any]] = []
    for symbol in sorted(grouped):
        items = grouped[symbol]
        open_items = [x for x in items if x.status == "open"]
        closed_items = [x for x in items if x.status == "closed"]
        symbol_outcomes = Counter((x.outcome_label or "unset") for x in closed_items)
        symbol_r = [float(x.realized_return_r) for x in closed_items if isinstance(x.realized_return_r, (int, float))]
        symbol_pct = [float(x.realized_return_pct) for x in closed_items if isinstance(x.realized_return_pct, (int, float))]

        symbols.append(
            {
                "symbol": symbol,
                "total_recommendations": len(items),
                "open_count": len(open_items),
                "closed_count": len(closed_items),
                "decision_counts": dict(Counter(x.decision for x in items)),
                "outcome_counts": dict(symbol_outcomes),
                "avg_realized_r": _avg(symbol_r),
                "avg_realized_pct": _avg(symbol_pct),
            }
        )

    return {
        "total_recommendations": len(records),
        "open_count": len(open_records),
        "closed_count": len(closed_records),
        "decision_counts": dict(decision_counts),
        "outcome_counts": dict(outcome_counts),
        "win_rate": win_rate,
        "avg_realized_r": _avg(realized_r),
        "avg_realized_pct": _avg(realized_pct),
        "latest_created_at": latest_created_at,
        "latest_closed_at": latest_closed_at,
        "latest_day": latest_day,
        "symbols": symbols,
    }


def write_report_json(report: dict[str, Any], out_path: str | Path) -> Path:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def export_records_csv(root: str | Path | None = None, out_path: str | Path | None = None) -> Path:
    records = load_recommendations(root)
    base = ensure_store(root)
    out = Path(out_path) if out_path is not None else (base / "report_records.csv")
    out.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "recommendation_id",
        "created_at",
        "source",
        "symbol",
        "day",
        "decision",
        "timeframe",
        "score",
        "entry",
        "stop",
        "target",
        "rationale",
        "invalidation",
        "status",
        "closed_at",
        "outcome_label",
        "realized_return_r",
        "realized_return_pct",
        "outcome_note",
        "metadata_json",
    ]

    with out.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for rec in records:
            writer.writerow(
                {
                    "recommendation_id": rec.recommendation_id,
                    "created_at": rec.created_at,
                    "source": rec.source,
                    "symbol": rec.symbol,
                    "day": rec.day,
                    "decision": rec.decision,
                    "timeframe": rec.timeframe,
                    "score": rec.score,
                    "entry": rec.entry,
                    "stop": rec.stop,
                    "target": rec.target,
                    "rationale": rec.rationale,
                    "invalidation": rec.invalidation,
                    "status": rec.status,
                    "closed_at": rec.closed_at,
                    "outcome_label": rec.outcome_label,
                    "realized_return_r": rec.realized_return_r,
                    "realized_return_pct": rec.realized_return_pct,
                    "outcome_note": rec.outcome_note,
                    "metadata_json": json.dumps(rec.metadata, ensure_ascii=False, sort_keys=True),
                }
            )

    return out
