"""Deterministic per-symbol edge memory for ranking feedback (no randomness)."""

from __future__ import annotations

import os
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, Optional


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(x)))


@dataclass(frozen=True)
class EdgeRecord:
    confidence: float
    momentum_abs: float
    selected_in_portfolio: bool
    low_conf: bool
    flat_momentum: bool


class SymbolEdgeMemory:
    """
    Last N cycles per symbol: confidence, momentum proxy, selection outcome.
    Produces edge_score in roughly [-0.2, 0.5] for ranking_score *= (1 + edge_score).
    """

    def __init__(self, *, maxlen: Optional[int] = None) -> None:
        n = maxlen if maxlen is not None else int(os.environ.get("BIST_EDGE_MEMORY_LEN", "20"))
        self._maxlen = max(3, min(100, n))
        self._ring: Dict[str, Deque[EdgeRecord]] = {}

    def record(
        self,
        symbol: str,
        *,
        confidence: float,
        momentum_abs: float,
        selected_in_portfolio: bool,
    ) -> None:
        sym = str(symbol).strip().upper()
        low_conf = confidence < 0.12
        flat_mom = momentum_abs < 0.002
        rec = EdgeRecord(
            confidence=float(confidence),
            momentum_abs=float(momentum_abs),
            selected_in_portfolio=bool(selected_in_portfolio),
            low_conf=low_conf,
            flat_momentum=flat_mom,
        )
        if sym not in self._ring:
            self._ring[sym] = deque(maxlen=self._maxlen)
        self._ring[sym].append(rec)

    def historical_edge_score(self, symbol: str) -> float:
        """Score from past records only."""
        sym = str(symbol).strip().upper()
        dq = self._ring.get(sym)
        if not dq:
            return 0.0
        recs = list(dq)
        n = len(recs)
        avg_c = sum(r.confidence for r in recs) / n
        avg_m = sum(r.momentum_abs for r in recs) / n
        pen = 0.0
        pen += sum(1 for r in recs if r.low_conf) * 0.04
        pen += sum(1 for r in recs if not r.selected_in_portfolio) * 0.03
        pen += sum(1 for r in recs if r.flat_momentum) * 0.03
        raw = 0.15 * avg_c + 0.35 * avg_m - pen / max(1, n)
        return _clamp(raw, -0.2, 0.5)

    def projected_edge_score(
        self,
        symbol: str,
        *,
        confidence: float,
        momentum_abs: float,
    ) -> float:
        """Historical edge + small deterministic nudge from current snapshot."""
        h = self.historical_edge_score(symbol)
        nudge = 0.06 * (float(confidence) - 0.15) + 0.12 * float(momentum_abs)
        return _clamp(h + nudge, -0.2, 0.5)

    def snapshot_all(self) -> Dict[str, float]:
        """Latest historical edge score per known symbol."""
        return {s: round(self.historical_edge_score(s), 6) for s in sorted(self._ring.keys())}


__all__ = ["EdgeRecord", "SymbolEdgeMemory"]
