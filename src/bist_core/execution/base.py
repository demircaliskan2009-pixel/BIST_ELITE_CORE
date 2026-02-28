"""ExecutionProvider protocol and ExecutionResult schema (stdlib, deterministic)."""

from __future__ import annotations

from typing import Any, Dict, List, Protocol, runtime_checkable


def execution_result(
    ok: bool,
    errors: List[str],
    broker: str,
    sent: int,
    details: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build ExecutionResult dict. Schema: ok, errors, broker, sent, details."""
    return {
        "ok": bool(ok),
        "errors": list(errors) if errors else [],
        "broker": str(broker),
        "sent": int(sent),
        "details": dict(details) if details is not None else {},
    }


@runtime_checkable
class ExecutionProvider(Protocol):
    """Common interface for order execution: submit_orders(orders, *, dry_run) -> ExecutionResult dict."""

    def submit_orders(self, orders: Dict[str, Any], *, dry_run: bool = True) -> Dict[str, Any]:
        """Submit orders; returns ExecutionResult (ok, errors, broker, sent, details)."""
        ...
