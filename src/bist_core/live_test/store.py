from __future__ import annotations

import json
import unicodedata
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .models import RecommendationRecord


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _default_root() -> Path:
    return Path("data/live_test")


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    return unicodedata.normalize("NFC", str(value))


def _normalize_obj(value: Any) -> Any:
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, list):
        return [_normalize_obj(x) for x in value]
    if isinstance(value, tuple):
        return tuple(_normalize_obj(x) for x in value)
    if isinstance(value, dict):
        return {_normalize_obj(k): _normalize_obj(v) for k, v in value.items()}
    return value


def ensure_store(root: str | Path | None = None) -> Path:
    base = Path(root) if root is not None else _default_root()
    base.mkdir(parents=True, exist_ok=True)
    return base


def recommendations_path(root: str | Path | None = None) -> Path:
    return ensure_store(root) / "recommendations.jsonl"


def _atomic_write_jsonl(path: Path, records: list[RecommendationRecord]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as fh:
        for rec in records:
            fh.write(json.dumps(rec.to_dict(), ensure_ascii=False) + "\n")
    tmp.replace(path)


def load_recommendations(root: str | Path | None = None) -> list[RecommendationRecord]:
    path = recommendations_path(root)
    if not path.exists():
        return []
    out: list[RecommendationRecord] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            text = line.strip()
            if not text:
                continue
            out.append(RecommendationRecord.from_dict(json.loads(text)))
    return out


def _make_id() -> str:
    return f"rec_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"


def append_recommendation(
    *,
    root: str | Path | None = None,
    source: str,
    symbol: str,
    day: str,
    decision: str,
    timeframe: str | None = None,
    score: float | None = None,
    entry: float | None = None,
    stop: float | None = None,
    target: float | None = None,
    rationale: str | None = None,
    invalidation: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> RecommendationRecord:
    record = RecommendationRecord(
        recommendation_id=_make_id(),
        created_at=_utc_now_iso(),
        source=_normalize_text(source) or "",
        symbol=(_normalize_text(symbol) or "").strip().upper(),
        day=(_normalize_text(day) or "").strip(),
        decision=(_normalize_text(decision) or "").strip().upper(),
        timeframe=None if timeframe is None else (_normalize_text(timeframe) or "").strip(),
        score=score,
        entry=entry,
        stop=stop,
        target=target,
        rationale=_normalize_text(rationale),
        invalidation=_normalize_text(invalidation),
        metadata={} if metadata is None else _normalize_obj(metadata),
    )
    path = recommendations_path(root)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
    return record


def close_recommendation(
    *,
    root: str | Path | None = None,
    recommendation_id: str,
    outcome_label: str,
    realized_return_r: float | None = None,
    realized_return_pct: float | None = None,
    outcome_note: str | None = None,
) -> RecommendationRecord:
    records = load_recommendations(root)
    target: RecommendationRecord | None = None
    for rec in records:
        if rec.recommendation_id == recommendation_id:
            target = rec
            break

    if target is None:
        raise KeyError(f"Recommendation not found: {recommendation_id}")

    target.status = "closed"
    target.closed_at = _utc_now_iso()
    target.outcome_label = (_normalize_text(outcome_label) or "").strip().lower()
    target.realized_return_r = realized_return_r
    target.realized_return_pct = realized_return_pct
    target.outcome_note = _normalize_text(outcome_note)

    _atomic_write_jsonl(recommendations_path(root), records)
    return target


def list_recommendations(
    *,
    root: str | Path | None = None,
    status: str | None = None,
    symbol: str | None = None,
    limit: int | None = None,
) -> list[RecommendationRecord]:
    records = load_recommendations(root)

    if status:
        wanted = str(status).strip().lower()
        records = [x for x in records if x.status.lower() == wanted]

    if symbol:
        wanted_symbol = str(symbol).strip().upper()
        records = [x for x in records if x.symbol == wanted_symbol]

    records = sorted(records, key=lambda x: (x.created_at, x.recommendation_id), reverse=True)

    if limit is not None:
        records = records[: max(int(limit), 0)]

    return records


def compute_stats(root: str | Path | None = None) -> dict[str, Any]:
    records = load_recommendations(root)

    total = len(records)
    open_records = [x for x in records if x.status == "open"]
    closed_records = [x for x in records if x.status == "closed"]

    decision_counts = Counter(x.decision for x in records)
    outcome_counts = Counter((x.outcome_label or "unset") for x in closed_records)

    closed_with_r = [x.realized_return_r for x in closed_records if isinstance(x.realized_return_r, (int, float))]
    wins = outcome_counts.get("win", 0)
    losses = outcome_counts.get("loss", 0)
    decided = wins + losses
    win_rate = None if decided == 0 else wins / decided
    avg_r = None if not closed_with_r else sum(float(x) for x in closed_with_r) / len(closed_with_r)

    latest_day = None if not records else max(x.day for x in records)
    unique_symbols = sorted({x.symbol for x in records})

    return {
        "total_recommendations": total,
        "open_count": len(open_records),
        "closed_count": len(closed_records),
        "decision_counts": dict(decision_counts),
        "outcome_counts": dict(outcome_counts),
        "win_rate": win_rate,
        "avg_realized_r": avg_r,
        "latest_day": latest_day,
        "unique_symbols": unique_symbols,
        "unique_symbols_count": len(unique_symbols),
    }
