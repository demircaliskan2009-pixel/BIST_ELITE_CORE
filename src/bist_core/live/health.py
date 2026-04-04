"""Health snapshot for live paper state."""

from __future__ import annotations

from typing import Any

from bist_core.live.state_store import LiveState


def get_health(state: LiveState) -> dict[str, Any]:
    return {
        "equity": state.equity,
        "open_positions": dict(state.positions),
        "positions": dict(state.positions),
        "daily_pnl": state.daily_pnl,
        "errors": list(state.errors[-50:]),
    }


__all__ = ["get_health"]
