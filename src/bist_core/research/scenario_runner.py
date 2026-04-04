"""Run multiple named replay scenarios (deterministic)."""

from __future__ import annotations

from typing import Any

from bist_core.replay.replay_engine import ReplayEngine


class ScenarioRunner:
    def run(self, trader: Any, scenarios: dict[str, list[Any]]) -> dict[str, list[Any]]:
        outputs: dict[str, list[Any]] = {}
        for name, data in scenarios.items():
            replay = ReplayEngine().replay(trader, data)
            outputs[str(name)] = replay
        return outputs


__all__ = ["ScenarioRunner"]
