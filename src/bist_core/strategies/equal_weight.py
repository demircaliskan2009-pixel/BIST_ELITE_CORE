from __future__ import annotations

from dataclasses import dataclass


@dataclass
class EqualWeightStrategy:
    name: str = "equal_weight"

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

        actionable: list[dict] = []
        if not advice_records:
            notes.extend(["no_advice", "no_actions"])
        else:
            for record in advice_records:
                decision = str(record.get("decision_raw", "PASS")).upper()
                if decision and decision != "PASS":
                    actionable.append(record)

        selected: list[dict] = []
        if actionable:
            ranked = sorted(
                actionable,
                key=lambda rec: (-float(rec.get("score", 0.0)), str(rec.get("symbol", ""))),
            )
            if isinstance(top_n, int) and top_n > 0:
                selected = ranked[:top_n]
            else:
                selected = ranked

        if not selected and "no_actions" not in notes:
            notes.append("no_actions")

        if selected:
            weight = 1.0 / len(selected)
            for record in selected:
                symbol = str(record.get("symbol", ""))
                decision = str(record.get("decision_raw", "BUY")).upper()
                side = "SELL" if decision == "SELL" else "BUY"
                actions.append(
                    {
                        "symbol": symbol,
                        "side": side,
                        "weight": round(weight, 6),
                    }
                )

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
