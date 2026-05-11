"""Execution plugin interface + providers (e.g. paper, dry_run)."""

from __future__ import annotations

from bist_core.execution.base import ExecutionProvider
from bist_core.execution.broker_adapter import (
    BrokerResponse,
    BrokerAdapter,
    BrokerPlacementProtocol,
    DummyBrokerAdapter,
    OrderStatus,
    PaperBrokerAdapter,
    StubBrokerAdapter,
)
from bist_core.execution.execution_engine import ExecutionEngine, Order
from bist_core.execution.paper import PaperExecutionProvider
from bist_core.execution.adapters.dry_run import DryRunExecutionProvider

__all__ = [
    "ExecutionProvider",
    "BrokerResponse",
    "BrokerAdapter",
    "BrokerPlacementProtocol",
    "DummyBrokerAdapter",
    "OrderStatus",
    "PaperBrokerAdapter",
    "StubBrokerAdapter",
    "ExecutionEngine",
    "Order",
    "PaperExecutionProvider",
    "DryRunExecutionProvider",
]
