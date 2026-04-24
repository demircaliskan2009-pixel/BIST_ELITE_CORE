"""PRDV3 §19 — persisted operational risk state with explicit transitions (deterministic)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

_ALLOWED = frozenset({"ACTIVE", "DE_RISK", "PAUSE", "RECOVER"})


@dataclass
class OperationalRiskFSM:
    """Tracks last state and transition edges for audit."""

    state: str = "ACTIVE"
    transition_count: int = 0
    last_transition: str | None = None
    history: List[str] = field(default_factory=list)
    _boot_done: bool = False

    def step(self, next_label: str) -> None:
        raw = str(next_label).strip().upper()
        nxt = raw if raw in _ALLOWED else "ACTIVE"
        if not self._boot_done:
            self._boot_done = True
            edge = f"BOOT->{nxt}"
            self.history.append(edge)
            if len(self.history) > 120:
                self.history = self.history[-120:]
            self.transition_count += 1
            self.last_transition = edge
            self.state = nxt
            return
        prev = self.state
        if prev != nxt:
            edge = f"{prev}->{nxt}"
            self.history.append(edge)
            if len(self.history) > 120:
                self.history = self.history[-120:]
            self.transition_count += 1
            self.last_transition = edge
        self.state = nxt

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state": str(self.state),
            "transition_count": int(self.transition_count),
            "last_transition": self.last_transition,
            "history_tail": list(self.history[-12:]),
        }

    def sync_from_dict(self, blob: Dict[str, Any] | None) -> None:
        if not blob:
            return
        try:
            st = str(blob.get("state", "")).strip().upper()
            if st in _ALLOWED:
                self.state = st
        except (TypeError, ValueError):
            pass
        try:
            self.transition_count = int(blob.get("transition_count", self.transition_count))
        except (TypeError, ValueError):
            pass
        lt = blob.get("last_transition")
        if lt is None or isinstance(lt, str):
            self.last_transition = lt
        hist = blob.get("history_tail")
        if isinstance(hist, list):
            self.history = [str(x) for x in hist][-120:]
        bd = blob.get("boot_done")
        if isinstance(bd, bool):
            self._boot_done = bd
        elif int(self.transition_count) > 0 or str(self.state).upper() in _ALLOWED:
            self._boot_done = True


__all__ = ["OperationalRiskFSM"]
