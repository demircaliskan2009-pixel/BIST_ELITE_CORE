"""In-memory state for live paper execution."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from bist_core.models.ohlcv import OHLCVBar


class LiveState:
    """Positions, last prints, rolling bar buffers, equity, dedup, risk."""

    def __init__(self, max_bar_buffer: int = 100) -> None:
        self.positions: dict[str, list[dict[str, Any]]] = {}
        self.last_prices: dict[str, float] = {}
        self.equity: float = 1.0
        self.daily_pnl: float = 0.0
        self.bar_buffers: dict[str, list[OHLCVBar]] = {}
        self.max_bar_buffer: int = max(50, int(max_bar_buffer))
        #: Stable identity for last processed bar per symbol (legacy; cursor supersedes)
        self.last_bar_id: dict[str, str] = {}
        #: Monotonic cursor: last fully processed bar as [timestamp, offset_key] (JSON list)
        self.last_bar_progress: dict[str, list] = {}
        #: Last decision snapshot per symbol (fail-closed diagnostics)
        self.last_signals: dict[str, Any] = {}
        self.errors: list[str] = []
        self.max_errors: int = 200
        self.order_seq: int = 0
        #: Persisted :class:`RiskEngine` fields (peak equity, streaks, trade stats).
        self.risk_blob: dict[str, Any] = {}
        #: Simulated replay: exclusive end index into ordered bars per symbol (live_runner).
        self.bar_index: dict[str, int] = {}

    def log_error(self, msg: str) -> None:
        self.errors.append(msg)
        if len(self.errors) > self.max_errors:
            self.errors = self.errors[-self.max_errors :]

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "positions": self.positions,
            "equity": self.equity,
            "daily_pnl": self.daily_pnl,
            "last_bar_id": self.last_bar_id,
            "last_bar_progress": dict(self.last_bar_progress),
            "order_seq": self.order_seq,
            "risk_blob": dict(self.risk_blob),
            "bar_index": dict(self.bar_index),
        }

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_jsonable(), indent=0), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> LiveState:
        p = Path(path)
        if not p.is_file():
            return cls()
        raw = json.loads(p.read_text(encoding="utf-8"))
        st = cls()
        st.positions = raw.get("positions", {})
        st.equity = float(raw.get("equity", 1.0))
        st.daily_pnl = float(raw.get("daily_pnl", 0.0))
        st.last_bar_id = dict(raw.get("last_bar_id", {}))
        lbp = raw.get("last_bar_progress")
        st.last_bar_progress = dict(lbp) if isinstance(lbp, dict) else {}
        st.order_seq = int(raw.get("order_seq", 0))
        rb = raw.get("risk_blob")
        st.risk_blob = dict(rb) if isinstance(rb, dict) else {}
        bi = raw.get("bar_index")
        st.bar_index = {}
        if isinstance(bi, dict):
            for k, v in bi.items():
                ks = str(k).strip()
                if not ks:
                    continue
                try:
                    st.bar_index[ks] = int(v)
                except (TypeError, ValueError):
                    pass
        return st


__all__ = ["LiveState"]
