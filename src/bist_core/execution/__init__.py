"""Execution plugin interface + providers (e.g. paper)."""
from __future__ import annotations

from bist_core.execution.base import ExecutionProvider
from bist_core.execution.paper import PaperExecutionProvider

__all__ = [
    "ExecutionProvider",
    "PaperExecutionProvider",
]
