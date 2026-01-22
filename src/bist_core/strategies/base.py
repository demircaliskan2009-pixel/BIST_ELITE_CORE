from __future__ import annotations

from typing import Protocol


class Strategy(Protocol):
    name: str

    def build_intent(
        self,
        *,
        day: str,
        universe: list[str],
        advice_records: list[dict],
        params: dict,
    ) -> dict:
        ...
