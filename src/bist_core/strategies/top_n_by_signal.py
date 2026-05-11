from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass
class TopNBySignalStrategy:
    name: str = "top_n_by_signal"

    def build_intent(
        self,
        *,
        day: str,
        universe: list[str],
        advice_records: list[dict],
        params: dict,
    ) -> dict:
        notes: list[str] = []
        actions: list[dict] = []
        top_n = params.get("top_n")

        symbols = [str(sym) for sym in universe if sym]
        if not symbols:
            notes.append("no_actions")
        else:
            ranked = sorted(
                symbols,
                key=lambda sym: (
                    int(hashlib.sha256(sym.encode("utf-8")).hexdigest(), 16),
                    sym,
                ),
            )
            if isinstance(top_n, int) and top_n > 0:
                selected = ranked[:top_n]
            else:
                selected = ranked
            if not selected:
                notes.append("no_actions")
            else:
                weight = 1.0 / len(selected)
                actions = [{"symbol": sym, "side": "BUY", "weight": round(weight, 6)} for sym in selected]

        actions = sorted(actions, key=lambda item: str(item.get("symbol", "")))
        notes = sorted(set(notes))
        return {
            "schema_version": 1,
            "strategy": {"name": self.name, "params": {"top_n": top_n}},
            "day": day,
            "universe_size": len(universe),
            "actions": actions,
            "notes": notes,
        }
