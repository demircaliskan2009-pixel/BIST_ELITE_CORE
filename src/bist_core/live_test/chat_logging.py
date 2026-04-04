from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .models import RecommendationRecord
from .store import append_recommendation

_NUM_PAT = r"[-+]?\d+(?:[.,]\d+)?"

def _to_float(text: str | None) -> float | None:
    if text is None:
        return None
    try:
        return float(str(text).replace(",", "."))
    except Exception:
        return None

def _extract_plan_values(text: str | None) -> tuple[float | None, float | None, float | None]:
    if not text:
        return None, None, None
    entry_m = re.search(r"entry\s+(" + _NUM_PAT + r")", text, flags=re.IGNORECASE)
    stop_m = re.search(r"stop\s+(" + _NUM_PAT + r")", text, flags=re.IGNORECASE)
    t1_m = re.search(r"\bt1\s+(" + _NUM_PAT + r")", text, flags=re.IGNORECASE)
    return (
        _to_float(entry_m.group(1)) if entry_m else None,
        _to_float(stop_m.group(1)) if stop_m else None,
        _to_float(t1_m.group(1)) if t1_m else None,
    )

def log_from_chat_payload(
    *,
    root: str | Path | None = None,
    response_json: dict[str, Any],
    source: str = "gateway_chat",
    timeframe: str | None = None,
    request_meta: dict[str, Any] | None = None,
) -> list[RecommendationRecord]:
    mode = str(response_json.get("mode", "")).strip().lower()
    payload = response_json.get("payload") or {}
    meta = {} if request_meta is None else dict(request_meta)

    out: list[RecommendationRecord] = []

    if mode == "ask":
        symbol = str(payload.get("symbol", "")).strip().upper()
        day = str(payload.get("day", "")).strip()
        decision = str(payload.get("decision_raw", payload.get("decision", ""))).strip().upper()
        score = _to_float(payload.get("score"))
        text = payload.get("text") or response_json.get("answer") or ""
        entry, stop, target = _extract_plan_values(text)

        rec = append_recommendation(
            root=root,
            source=source,
            symbol=symbol,
            day=day,
            decision=decision,
            timeframe=timeframe,
            score=score,
            entry=entry,
            stop=stop,
            target=target,
            rationale=str(text).strip() or None,
            invalidation=None,
            metadata={"mode": "ask", **meta},
        )
        out.append(rec)
        return out

    if mode == "scan":
        day = str(payload.get("day", "")).strip()
        ranked = payload.get("ranked") or []
        for item in ranked:
            symbol = str(item.get("symbol", "")).strip().upper()
            score = _to_float(item.get("score"))
            rationale = item.get("rationale")
            rec = append_recommendation(
                root=root,
                source=source,
                symbol=symbol,
                day=day,
                decision="SCAN_CANDIDATE",
                timeframe=timeframe,
                score=score,
                entry=None,
                stop=None,
                target=None,
                rationale=None if rationale is None else str(rationale),
                invalidation=None,
                metadata={"mode": "scan", **meta},
            )
            out.append(rec)
        return out

    raise ValueError(f"Unsupported chat response mode for logging: {mode!r}")

def load_response_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))
