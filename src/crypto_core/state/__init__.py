"""crypto_core.state — Global System State Engine.

Single source of truth for system operational state (PRD §1.29).
All upstream modules query this engine before taking any action.
"""

from __future__ import annotations

from crypto_core.state.engine import SystemStateEngine, compute_shs
from crypto_core.state.models import (
    SignalInputs,
    StateSnapshot,
    SystemState,
    TransitionRecord,
    is_at_least,
    state_severity,
)

__all__ = [
    "SystemStateEngine",
    "SystemState",
    "SignalInputs",
    "StateSnapshot",
    "TransitionRecord",
    "compute_shs",
    "is_at_least",
    "state_severity",
]
