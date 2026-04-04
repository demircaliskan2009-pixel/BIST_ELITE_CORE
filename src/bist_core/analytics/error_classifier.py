"""Bucket audit risk events by reason (deterministic counts)."""

from __future__ import annotations

from typing import Any


class ErrorClassifier:
    def classify(self, audit_logs: list[dict[str, Any]]) -> dict[str, int]:
        counts: dict[str, int] = {}

        for log in audit_logs:
            if not isinstance(log, dict):
                continue
            if log.get("event") != "risk":
                continue
            data = log.get("data")
            if not isinstance(data, dict):
                reason = "unknown"
            else:
                r = data.get("reason", "unknown")
                reason = str(r) if r is not None else "unknown"
            counts[reason] = counts.get(reason, 0) + 1

        return counts


__all__ = ["ErrorClassifier"]
