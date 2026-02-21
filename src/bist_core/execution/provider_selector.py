"""FAZ580: Execution provider selector from env — default DryRun, opt-in real_skeleton."""
from __future__ import annotations

import os
from typing import Any

from bist_core.execution.base import ExecutionProvider
from bist_core.execution.adapters.dry_run import DryRunExecutionProvider
from bist_core.execution.adapters.real_broker_skeleton import RealBrokerExecutionProvider


def get_execution_provider_from_env() -> ExecutionProvider:
    """
    Return ExecutionProvider based on BIST_EXEC_PROVIDER env.
    - default (unset or empty): DryRunExecutionProvider
    - real_skeleton: RealBrokerExecutionProvider(transport=None) — fails closed on live submit
    """
    provider = (os.environ.get("BIST_EXEC_PROVIDER") or "").strip().lower()
    if provider == "real_skeleton":
        return RealBrokerExecutionProvider(transport=None)
    return DryRunExecutionProvider()
