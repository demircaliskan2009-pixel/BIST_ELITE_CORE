"""Models: plugin interface (base) + dataclasses for backward compatibility."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, List, Tuple

from bist_core.models.base import ModelPlugin
from bist_core.models.baseline import BaselineModel

# OpenAIModel: optional, requires pip install openai and OPENAI_API_KEY env
try:
    from bist_core.models.openai_model import OpenAIModel
except ImportError:
    OpenAIModel = None  # type: ignore


@dataclass
class EODBar:
    symbol: str
    date: date
    close: float
    high: float
    low: float
    volume: int
    turnover_tl: int


@dataclass
class PriceBand:
    price_min: float
    price_max: float
    tick: float
    up_limit_pct: float
    down_limit_pct: float


@dataclass
class KapEvent:
    symbol: str
    ts_trt: datetime
    title: str
    body: str


@dataclass
class EventRecord:
    symbol: str
    ts: str
    kind: str
    title: str
    url: str | None = None
    tags: List[str] | None = None
    payload: Dict[str, Any] | None = None


def validate_events(rows: List[Dict[str, Any]]) -> Tuple[List[EventRecord], List[str]]:
    events: List[EventRecord] = []
    errors: List[str] = []
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"SchemaError:row={idx} not a dict")
            continue
        symbol = row.get("symbol")
        ts = row.get("ts")
        kind = row.get("kind")
        title = row.get("title")
        if not all(isinstance(v, str) and v.strip() for v in [symbol, ts, kind, title]):
            errors.append(f"SchemaError:row={idx} missing required fields")
            continue
        try:
            _ = datetime.fromisoformat(ts)
        except Exception:
            errors.append(f"SchemaError:row={idx} invalid ts")
            continue
        url = row.get("url")
        if url is not None and not isinstance(url, str):
            errors.append(f"SchemaError:row={idx} invalid url")
            continue
        tags = row.get("tags")
        if tags is not None and (not isinstance(tags, list) or not all(isinstance(t, str) for t in tags)):
            errors.append(f"SchemaError:row={idx} invalid tags")
            continue
        payload = row.get("payload")
        if payload is not None and not isinstance(payload, dict):
            errors.append(f"SchemaError:row={idx} invalid payload")
            continue
        events.append(
            EventRecord(
                symbol=symbol,
                ts=ts,
                kind=kind,
                title=title,
                url=url,
                tags=tags,
                payload=payload,
            )
        )
    return events, errors


__all__ = [
    "ModelPlugin",
    "BaselineModel",
    "EODBar",
    "PriceBand",
    "KapEvent",
    "EventRecord",
    "validate_events",
]
