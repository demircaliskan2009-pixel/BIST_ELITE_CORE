"""Stub broker adapter for live execution (requires broker config; deterministic)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from bist_core.execution.base import execution_result


class StubExecutionProvider:
    """
    Stub execution provider for live mode. Requires broker config (dict or path).
    submit_orders: dry_run returns ok; live returns ok with sent=0 (no real send).
    """

    def __init__(self, config: Dict[str, Any] | Path | str) -> None:
        if isinstance(config, (Path, str)):
            path = Path(config)
            if not path.is_file():
                raise ValueError("live_execution_missing_broker_config")
            with path.open("r", encoding="utf-8") as f:
                self._config = json.load(f)
        else:
            self._config = dict(config) if config else {}
        if not self._config:
            raise ValueError("live_execution_missing_broker_config")

    def submit_orders(self, orders: Dict[str, Any], *, dry_run: bool = True) -> Dict[str, Any]:
        actions = orders.get("actions") or []
        sent = 0 if dry_run else 0
        return execution_result(
            ok=True,
            errors=[],
            broker="stub",
            sent=sent,
            details={"dry_run": dry_run, "config_present": True},
        )
