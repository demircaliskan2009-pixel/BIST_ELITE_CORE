"""Broker abstraction layer for offline, deterministic adapters.

FAZ598a: Defines the minimal contract used by offline broker runners.
No network, no secrets. All implementations must be deterministic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, Optional


class BrokerAdapter(ABC):
    """Abstract base class for broker adapters used by offline runners.

    Implementations are responsible for validating local filesystem
    inputs only. They MUST NOT perform any network or side-effectful
    operations beyond basic file existence checks.
    """

    @abstractmethod
    def submit_order_ticket(self, ticket_path: str, day: str) -> Dict[str, object]:
        """Register an order ticket for execution.

        Implementations should:
        - Validate that ``ticket_path`` exists and is a file.
        - Return a deterministic metadata dict describing how to proceed.

        The returned metadata MUST be JSON-serializable and MUST NOT
        include secrets or environment-dependent data.
        """

    @abstractmethod
    def fetch_fills(self, day: str, fills_path: Optional[str]) -> str:
        """Resolve and validate the path to a fills CSV for a given day.

        Implementations should:
        - Require ``fills_path`` in modes that depend on manual uploads.
        - Validate that the provided path exists and is a file.

        Returns the absolute path to the fills CSV as a string.
        """
