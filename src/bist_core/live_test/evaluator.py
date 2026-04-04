from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from .models import RecommendationRecord
from .store import close_recommendation, list_recommendations


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except Exception:
        return None


@dataclass
class _EvalResult:
    action: str
    outcome_label: str | None = None
    realized_return_r: float | None = None
    realized_return_pct: float | None = None
    outcome_note: str | None = None


class SnapshotLookup:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self._days: list[str] | None = None
        self._cache: dict[str, dict[str, dict[str, float | str]]] = {}

    def available_days(self) -> list[str]:
        if self._days is not None:
            return self._days

        out: list[str] = []
        if self.root.exists():
            for entry in self.root.iterdir():
                if not entry.is_dir():
                    continue
                try:
                    date.fromisoformat(entry.name)
                except ValueError:
                    continue
                out.append(entry.name)
        self._days = sorted(out)
        return self._days

    def _load_day(self, day: str) -> dict[str, dict[str, float | str]]:
        if day in self._cache:
            return self._cache[day]

        out: dict[str, dict[str, float | str]] = {}
        path = self.root / day / "snapshot.csv"
        if not path.exists():
            self._cache[day] = out
            return out

        with path.open("r", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                symbol = str(row.get("symbol", "")).strip().upper()
                if not symbol:
                    continue

                try:
                    out[symbol] = {
                        "date": day,
                        "symbol": symbol,
                        "open": float(row["open"]),
                        "high": float(row["high"]),
                        "low": float(row["low"]),
                        "close": float(row["close"]),
                    }
                except Exception:
                    continue

        self._cache[day] = out
        return out

    def bar(self, day: str, symbol: str) -> dict[str, float | str] | None:
        return self._load_day(day).get(str(symbol).strip().upper())


def _close_payload(
    *,
    label: str,
    realized_r: float | None = None,
    realized_pct: float | None = None,
    note: str | None = None,
) -> _EvalResult:
    return _EvalResult(
        action="close",
        outcome_label=label,
        realized_return_r=None if realized_r is None else round(float(realized_r), 6),
        realized_return_pct=None if realized_pct is None else round(float(realized_pct), 6),
        outcome_note=note,
    )


def _evaluate_record(
    rec: RecommendationRecord,
    lookup: SnapshotLookup,
    max_holding_days: int,
) -> _EvalResult:
    if rec.status.lower() != "open":
        return _EvalResult(action="noop", outcome_note="status_not_open")

    if rec.entry is None or rec.stop is None or rec.target is None:
        return _close_payload(
            label="skipped",
            note="missing_trade_plan(entry/stop/target)",
        )

    risk = float(rec.entry) - float(rec.stop)
    if risk <= 0:
        return _close_payload(
            label="invalid_plan",
            note=f"non_positive_risk(entry={rec.entry}, stop={rec.stop})",
        )

    days = [d for d in lookup.available_days() if d >= rec.day]
    if not days:
        return _EvalResult(action="noop", outcome_note="no_snapshot_days_available")

    eval_days = days[: max(int(max_holding_days), 1)]
    active = False
    last_bar: dict[str, float | str] | None = None
    entry_day: str | None = None

    for day in eval_days:
        bar = lookup.bar(day, rec.symbol)
        if bar is None:
            continue

        last_bar = bar
        low = float(bar["low"])
        high = float(bar["high"])
        close = float(bar["close"])

        if not active:
            if low <= float(rec.entry) <= high:
                active = True
                entry_day = day
            else:
                continue

        stop_hit = low <= float(rec.stop)
        target_hit = high >= float(rec.target)

        if stop_hit and target_hit:
            return _close_payload(
                label="ambiguous",
                note=f"stop_and_target_hit_same_day(day={day}, entry_day={entry_day})",
            )

        if target_hit:
            realized_r = (float(rec.target) - float(rec.entry)) / risk
            realized_pct = ((float(rec.target) - float(rec.entry)) / float(rec.entry)) * 100.0
            return _close_payload(
                label="win",
                realized_r=realized_r,
                realized_pct=realized_pct,
                note=f"target_hit(day={day}, entry_day={entry_day})",
            )

        if stop_hit:
            realized_r = (float(rec.stop) - float(rec.entry)) / risk
            realized_pct = ((float(rec.stop) - float(rec.entry)) / float(rec.entry)) * 100.0
            return _close_payload(
                label="loss",
                realized_r=realized_r,
                realized_pct=realized_pct,
                note=f"stop_hit(day={day}, entry_day={entry_day})",
            )

        _ = close  # explicit for readability

    if active and last_bar is not None:
        last_close = float(last_bar["close"])
        realized_r = (last_close - float(rec.entry)) / risk
        realized_pct = ((last_close - float(rec.entry)) / float(rec.entry)) * 100.0
        return _close_payload(
            label="expired",
            realized_r=realized_r,
            realized_pct=realized_pct,
            note=f"holding_window_expired(last_day={last_bar['date']}, entry_day={entry_day})",
        )

    return _close_payload(
        label="no_entry",
        realized_r=0.0,
        realized_pct=0.0,
        note=f"entry_not_triggered_within_{len(eval_days)}_trading_days",
    )


def evaluate_open_recommendations(
    *,
    root: str | Path | None = None,
    snapshot_root: str | Path = "data/eod/snapshots",
    max_holding_days: int = 10,
    limit: int | None = None,
) -> dict[str, Any]:
    open_records = list_recommendations(root=root, status="open", limit=limit)
    lookup = SnapshotLookup(snapshot_root)

    outcome_counts: Counter[str] = Counter()
    closed_ids: list[str] = []
    noop_ids: list[str] = []

    for rec in open_records:
        result = _evaluate_record(rec, lookup, max_holding_days=max_holding_days)

        if result.action == "close" and result.outcome_label is not None:
            close_recommendation(
                root=root,
                recommendation_id=rec.recommendation_id,
                outcome_label=result.outcome_label,
                realized_return_r=result.realized_return_r,
                realized_return_pct=result.realized_return_pct,
                outcome_note=result.outcome_note,
            )
            outcome_counts[result.outcome_label] += 1
            closed_ids.append(rec.recommendation_id)
        else:
            noop_ids.append(rec.recommendation_id)

    return {
        "ok": True,
        "snapshot_root": str(Path(snapshot_root)),
        "processed_open_count": len(open_records),
        "closed_count": len(closed_ids),
        "noop_count": len(noop_ids),
        "outcome_counts": dict(outcome_counts),
        "closed_ids": closed_ids,
        "noop_ids": noop_ids,
        "max_holding_days": int(max_holding_days),
    }
