"""Execution adapters: paper, live (stub + registry) with strict dry-run vs live separation."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from bist_core.execution.base import ExecutionProvider
from bist_core.execution.adapters.stub_broker import StubExecutionProvider
from bist_core.execution.adapters.registry import get_execution_provider


def resolve_execution_provider(
    execution: str,
    broker_name: str,
    *,
    outdir: Optional[Path] = None,
    day: Optional[str] = None,
    broker_config_path: Optional[Path] = None,
    broker_config: Optional[Dict[str, Any]] = None,
) -> Tuple[Optional[Any], Optional[str]]:
    """
    Resolve execution provider by execution mode and broker name.
    Returns (provider, error_msg). If error_msg is set, provider is None (fail-closed).
    execution: "paper" | "live"
    broker_name: e.g. "paper", "stub", or a name registered via registry.
    For live: broker_config_path or broker_config must be set; else returns (None, "live_execution_missing_broker_config").
    """
    if execution == "paper" or broker_name == "paper":
        if outdir is not None and day is not None:
            from bist_core.execution.paper import PaperExecutionProvider

            return (PaperExecutionProvider(outdir, day), None)
        return (None, "execution_missing_outdir_day")
    if execution == "live":
        if broker_config_path is None and broker_config is None:
            return (None, "live_execution_missing_broker_config")
        factory = get_execution_provider(broker_name)
        if factory is not None:
            try:
                provider = factory(
                    broker_config_path=broker_config_path,
                    broker_config=broker_config,
                    outdir=outdir,
                    day=day,
                    broker_name=broker_name,
                    execution=execution,
                )
                return (provider, None)
            except (ValueError, TypeError) as e:
                return (None, str(e))
        if broker_config_path and broker_config_path.is_file():
            try:
                return (StubExecutionProvider(broker_config_path), None)
            except ValueError as e:
                return (None, str(e))
        if broker_config:
            try:
                return (StubExecutionProvider(broker_config), None)
            except ValueError as e:
                return (None, str(e))
        return (None, "live_execution_missing_broker_config")
    return (None, "unknown_execution_or_broker")


__all__ = ["ExecutionProvider", "StubExecutionProvider", "get_execution_provider"]
