"""Stub broker adapter for live execution (requires broker config; FAZ72: calls through BrokerAdapter when live)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from bist_core.execution.base import execution_result
from bist_core.execution.broker_adapter import StubBrokerAdapter


class StubExecutionProvider:
    """
    Stub execution provider for live mode. Requires broker config (dict or path).
    FAZ72: When not dry_run, calls through broker adapter (place_orders); otherwise returns ok with sent=0.
    """

    def __init__(
        self,
        config: Dict[str, Any] | Path | str,
        broker_adapter: Optional[Any] = None,
    ) -> None:
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
        if broker_adapter is not None:
            self._adapter: Optional[Any] = broker_adapter
        else:
            self._adapter = StubBrokerAdapter(self._config)

    def submit_orders(self, orders: Dict[str, Any], *, dry_run: bool = True) -> Dict[str, Any]:
        if dry_run:
            actions = orders.get("actions") or []
            sent = 0
            return execution_result(
                ok=True,
                errors=[],
                broker="stub",
                sent=sent,
                details={"dry_run": True, "config_present": True},
            )
        # FAZ72: live path — call through broker adapter
        adapter = self._adapter
        if adapter is None:
            return execution_result(
                ok=True,
                errors=[],
                broker="stub",
                sent=0,
                details={"dry_run": False, "adapter_missing": True},
            )
        result = adapter.place_orders(orders)
        ok = result.get("ok", False)
        errors = result.get("errors") or []
        fills = result.get("fills") or []
        order_ids = result.get("order_ids") or []
        sent = len(order_ids) if ok else 0
        return execution_result(
            ok=ok,
            errors=errors,
            broker="stub",
            sent=sent,
            details={"fills": fills, "order_ids": order_ids},
        )
