"""FAZ600: Real broker prep stub.

Offline-only placeholder for a future real broker adapter.
No network, no secrets; always fails closed.
"""
from __future__ import annotations

from typing import Dict, Optional

from bist_core.broker.interfaces import BrokerAdapter


class RealBrokerStub(BrokerAdapter):
    """Placeholder adapter that explicitly blocks real broker usage.

    This class is never meant to talk to a real broker. It exists only
    to make the wiring explicit and to fail-closed until a proper,
    out-of-repo transport is injected.
    """

    def submit_order_ticket(self, ticket_path: str, day: str) -> Dict[str, object]:
        return {
            "broker": "real_stub",
            "day": day,
            "ticket_path": ticket_path,
            "ok": False,
            "mode": "stub_blocked",
            "errors": ["real_broker_not_configured"],
            "details": {
                "message": (
                    "Real broker is not configured in this repo. "
                    "See docs/secrets_policy.md and configure an out-of-repo "
                    "transport before enabling live execution."
                )
            },
        }

    def fetch_fills(self, day: str, fills_path: Optional[str]) -> str:
        raise RuntimeError(
            "RealBrokerStub does not handle fills. "
            "Use ManualBroker and broker_run.ps1 -Mode manual instead."
        )

