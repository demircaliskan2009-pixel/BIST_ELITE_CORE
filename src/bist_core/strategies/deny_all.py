from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DenyAllStrategy:
    name: str = "deny_all"

    def build_intent(
        self,
        *,
        day: str,
        universe: list[str],
        advice_records: list[dict],
        params: dict,
    ) -> dict:
        notes = ["no_actions"]
        return {
            "schema_version": 1,
            "strategy": {"name": self.name, "params": {}},
            "day": day,
            "universe_size": len(universe),
            "actions": [],
            "notes": notes,
        }
