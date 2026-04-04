from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class RecommendationRecord:
    recommendation_id: str
    created_at: str
    source: str
    symbol: str
    day: str
    decision: str
    timeframe: str | None = None
    score: float | None = None
    entry: float | None = None
    stop: float | None = None
    target: float | None = None
    rationale: str | None = None
    invalidation: str | None = None
    status: str = "open"
    closed_at: str | None = None
    outcome_label: str | None = None
    realized_return_r: float | None = None
    realized_return_pct: float | None = None
    outcome_note: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RecommendationRecord":
        return cls(**payload)
