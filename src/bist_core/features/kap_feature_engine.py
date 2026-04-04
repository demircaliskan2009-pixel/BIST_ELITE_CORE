"""KAP feature bundle for edge modulation — no standalone trades."""

from __future__ import annotations

from typing import Any

from bist_core.features.kap_classifier import classify_kap_event
from bist_core.features.kap_time_decay import compute_time_decay


class KapFeatureEngine:
    """Build ``kap_feature`` dict from a raw RSS-shaped item and wall-clock ``now_ts``."""

    def build_feature(self, item: dict[str, Any], now_ts: int) -> dict[str, Any] | None:
        classified = classify_kap_event(item)
        if not classified:
            return None

        try:
            nt = int(now_ts)
        except (TypeError, ValueError):
            return None

        decay = compute_time_decay(int(classified["timestamp"]), nt)
        if decay <= 0.0:
            return None

        kap_alpha = float(classified["strength"]) * float(decay)
        age_min = (nt - int(classified["timestamp"])) / 60.0

        return {
            "symbol": str(classified["symbol"]),
            "kap_event": str(classified["event_type"]),
            "kap_alpha": float(kap_alpha),
            "kap_age_min": float(age_min),
            "event_ts": int(classified["timestamp"]),
        }


__all__ = ["KapFeatureEngine"]
