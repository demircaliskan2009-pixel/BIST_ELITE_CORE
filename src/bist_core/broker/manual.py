"""Manual broker adapter for offline workflows.

FAZ598a: Offline, secrets-free adapter used when a human
submits tickets and uploads fills CSV files manually.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from bist_core.broker.interfaces import BrokerAdapter


class ManualBroker(BrokerAdapter):
    """Offline manual broker.

    This adapter is intentionally minimal and deterministic:
    - It validates that expected files exist.
    - It returns simple metadata / resolved paths.
    - It performs no network calls and does not inspect file contents.
    """

    def submit_order_ticket(self, ticket_path: str, day: str) -> Dict[str, object]:
        path = Path(ticket_path)
        if not path.is_file():
            raise FileNotFoundError(f"order ticket not found: {path}")

        resolved = path.resolve()
        return {
            "broker": "manual",
            "day": day,
            "ticket_path": str(resolved),
            "mode": "offline_manual",
            "instructions": (
                "Send the order ticket to the broker via your approved "
                "offline channel, then upload the official fills CSV and "
                "run broker_run.ps1 to import fills."
            ),
        }

    def fetch_fills(self, day: str, fills_path: Optional[str]) -> str:
        if not fills_path:
            raise ValueError("fills_path is required in manual mode")

        path = Path(fills_path)
        if not path.is_file():
            raise FileNotFoundError(f"fills CSV not found: {path}")

        return str(path.resolve())

