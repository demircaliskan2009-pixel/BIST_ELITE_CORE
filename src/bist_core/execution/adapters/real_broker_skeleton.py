"""FAZ580: Real broker execution provider skeleton — offline-first, no network, no secrets."""

from __future__ import annotations

from typing import Any, Dict, Optional

from bist_core.execution.base import execution_result
from bist_core.execution.adapters.dry_run import DryRunExecutionProvider


class RealBrokerExecutionProvider:
    """
    Skeleton for future real broker integration. Offline-first: no network, no secrets.
    - dry_run=True: behaves like DryRunExecutionProvider (validate only).
    - dry_run=False: requires injected transport; if missing => fail-closed (broker_transport_missing).
    """

    def __init__(self, transport: Optional[Any] = None) -> None:
        self._transport = transport
        self._dry_run_provider = DryRunExecutionProvider()

    def submit_orders(self, orders: Dict[str, Any], *, dry_run: bool = True) -> Dict[str, Any]:
        """
        Validate schema, check gates. If dry_run: validate only. If live: require transport.
        Fail-closed: invalid schema, gates blocked, or transport missing => ok=False.
        """
        if dry_run:
            r = self._dry_run_provider.submit_orders(orders, dry_run=True)
            return {**r, "broker": "real_skeleton"}

        # dry_run=False: require transport; never call network
        if self._transport is None:
            return execution_result(
                ok=False,
                errors=["broker_transport_missing"],
                broker="real_skeleton",
                sent=0,
                details={"reason": "transport required for live; inject transport or use fixture mode"},
            )

        # Transport present: fixture mode (e.g. StubBrokerAdapter) — no network
        result = self._transport.place_orders(orders)
        ok = result.get("ok", False)
        errors = result.get("errors") or []
        order_ids = result.get("order_ids") or []
        fills = result.get("fills") or []
        sent = len(order_ids) if ok else 0
        return execution_result(
            ok=ok,
            errors=errors,
            broker="real_skeleton",
            sent=sent,
            details={"fills": fills, "order_ids": order_ids},
        )
