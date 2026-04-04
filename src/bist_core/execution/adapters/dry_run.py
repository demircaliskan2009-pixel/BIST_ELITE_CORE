"""FAZ573: Dry-run broker adapter — validates orders, prints deterministic summary. No network, no secrets."""

from __future__ import annotations

import io
import json
from typing import Any, Dict

from bist_core.execution.base import execution_result
from bist_core.orders.schema import validate_orders_intent_v2


def _format_summary(orders: Dict[str, Any]) -> str:
    """Deterministic summary: day, action count, symbols sorted."""
    day = orders.get("day") or ""
    actions = orders.get("actions") or []
    symbols = sorted(
        (a.get("symbol") or "").strip() for a in actions if isinstance(a, dict) and (a.get("symbol") or "").strip()
    )
    lines = [
        "dry_run_summary",
        f"day={day}",
        f"actions={len(actions)}",
        f"symbols={','.join(symbols)}",
    ]
    return "\n".join(lines)


class DryRunExecutionProvider:
    """
    Dry-run execution provider. Validates orders_intent schema, enforces risk gate
    (fail if gates.blocked). Prints deterministic summary. No network, no secrets.
    """

    def __init__(self) -> None:
        pass

    def submit_orders(self, orders: Dict[str, Any], *, dry_run: bool = True) -> Dict[str, Any]:
        """
        Validate schema, check gates, print summary. Returns ExecutionResult.
        Fail-closed: invalid schema or gates blocked => ok=False.
        """
        # Schema validation
        ok_schema, schema_errors = validate_orders_intent_v2(orders)
        if not ok_schema:
            return execution_result(
                ok=False,
                errors=schema_errors,
                broker="dry_run",
                sent=0,
                details={"schema_errors": schema_errors},
            )

        # Risk gate: if gates report present and blocked, fail-closed
        gates = orders.get("gates") if isinstance(orders.get("gates"), dict) else None
        if gates is not None and gates.get("blocked") is True:
            return execution_result(
                ok=False,
                errors=["risk_gate_blocked"],
                broker="dry_run",
                sent=0,
                details={"gates": gates},
            )

        actions = orders.get("actions") or []
        sent = len(actions)
        summary = _format_summary(orders)

        return execution_result(
            ok=True,
            errors=[],
            broker="dry_run",
            sent=sent,
            details={"summary": summary, "dry_run": True},
        )


def dry_run_validate_and_print(orders: Dict[str, Any], out: io.TextIOBase | None = None) -> tuple[bool, str]:
    """
    Standalone validation + deterministic print. Returns (ok, summary).
    Use for tools/CLI that need to validate and print without ExecutionProvider.
    """
    ok_schema, schema_errors = validate_orders_intent_v2(orders)
    if not ok_schema:
        summary = json.dumps({"ok": False, "errors": schema_errors}, sort_keys=True)
        if out:
            out.write(summary + "\n")
        return False, summary

    gates = orders.get("gates") if isinstance(orders.get("gates"), dict) else None
    if gates is not None and gates.get("blocked") is True:
        summary = json.dumps({"ok": False, "errors": ["risk_gate_blocked"]}, sort_keys=True)
        if out:
            out.write(summary + "\n")
        return False, summary

    summary = _format_summary(orders)
    if out:
        out.write(summary + "\n")
    return True, summary
