"""In-memory audit trail — deterministic, JSON-safe, no external I/O."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List


def _json_safe(obj: Any) -> Any:
    try:
        return json.loads(json.dumps(obj, default=str))
    except Exception:
        return {"_error": "non_serializable", "repr": repr(obj)}


class AuditLogger:
    """Append-only audit records with UTC timestamps."""

    def __init__(self) -> None:
        self.logs: List[Dict[str, Any]] = []

    def log(self, record: dict) -> None:
        if not isinstance(record, dict):
            record = {"_invalid": repr(record)}
        base = dict(record)
        base["timestamp"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        safe = _json_safe(base)
        self.logs.append(safe)

    def get_logs(self) -> List[Dict[str, Any]]:
        return list(self.logs)


__all__ = ["AuditLogger"]
