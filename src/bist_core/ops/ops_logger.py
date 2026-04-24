"""Operations logger — PRD §14 auditability layer.

Records decisions, orders, trades, risk rejections, and validation
results as append-only JSONL files.  Deterministic serialization,
atomic writes, no network.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence

# ---------------------------------------------------------------------------
# JSONL writer (atomic append)
# ---------------------------------------------------------------------------

def _append_jsonl(path: Path, record: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, sort_keys=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def _write_jsonl_batch(path: Path, records: Sequence[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped:
                rows.append(json.loads(stripped))
    return rows


# ---------------------------------------------------------------------------
# Timestamp helper
# ---------------------------------------------------------------------------

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# OpsLogger
# ---------------------------------------------------------------------------

class OpsLogger:
    """Append-only JSONL logger for trading operations."""

    def __init__(self, log_dir: Path | str) -> None:
        self._dir = Path(log_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    @property
    def log_dir(self) -> Path:
        return self._dir

    @property
    def decisions_path(self) -> Path:
        return self._dir / "decisions.jsonl"

    @property
    def orders_path(self) -> Path:
        return self._dir / "orders.jsonl"

    @property
    def trades_path(self) -> Path:
        return self._dir / "trades.jsonl"

    @property
    def validation_path(self) -> Path:
        return self._dir / "validation.jsonl"

    # -- Decision logging -------------------------------------------------

    def log_decision(
        self,
        symbol: str,
        entry: float,
        stop: float,
        target: float,
        timestamp: str,
        reasoning: str = "",
        **extra: Any,
    ) -> Dict[str, Any]:
        record = {
            "kind": "decision",
            "symbol": str(symbol).upper().strip(),
            "entry": entry,
            "stop": stop,
            "target": target,
            "timestamp": timestamp,
            "reasoning": reasoning,
            "logged_at": _utc_now_iso(),
        }
        record.update(extra)
        _append_jsonl(self.decisions_path, record)
        return record

    # -- Order logging ----------------------------------------------------

    def log_order(
        self,
        order_id: str,
        symbol: str,
        order_type: str,
        size: int,
        entry: float,
        status: str,
        **extra: Any,
    ) -> Dict[str, Any]:
        record = {
            "kind": "order",
            "order_id": order_id,
            "symbol": str(symbol).upper().strip(),
            "type": order_type,
            "size": size,
            "entry": entry,
            "status": status,
            "logged_at": _utc_now_iso(),
        }
        record.update(extra)
        _append_jsonl(self.orders_path, record)
        return record

    # -- Trade logging ----------------------------------------------------

    def log_trade(
        self,
        entry_time: str,
        exit_time: str,
        entry_price: float,
        exit_price: float,
        pnl: float,
        r_multiple: float | None = None,
        **extra: Any,
    ) -> Dict[str, Any]:
        record = {
            "kind": "trade",
            "entry_time": entry_time,
            "exit_time": exit_time,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "pnl": pnl,
            "r_multiple": r_multiple,
            "logged_at": _utc_now_iso(),
        }
        record.update(extra)
        _append_jsonl(self.trades_path, record)
        return record

    # -- Risk rejection logging -------------------------------------------

    def log_risk_rejection(
        self,
        symbol: str,
        reason: str,
        violations: Sequence[str] | None = None,
        **extra: Any,
    ) -> Dict[str, Any]:
        record = {
            "kind": "risk_rejection",
            "symbol": str(symbol).upper().strip(),
            "reason": reason,
            "violations": list(violations) if violations else [],
            "logged_at": _utc_now_iso(),
        }
        record.update(extra)
        _append_jsonl(self.decisions_path, record)
        return record

    # -- Validation logging -----------------------------------------------

    def log_validation(
        self,
        valid: bool,
        metrics: Dict[str, Any],
        regime_metrics: Dict[str, Any] | None = None,
        warnings: Sequence[str] | None = None,
        **extra: Any,
    ) -> Dict[str, Any]:
        record = {
            "kind": "validation",
            "valid": valid,
            "metrics": dict(metrics),
            "regime_metrics": dict(regime_metrics) if regime_metrics else {},
            "warnings": list(warnings) if warnings else [],
            "logged_at": _utc_now_iso(),
        }
        record.update(extra)
        _append_jsonl(self.validation_path, record)
        return record

    # -- Batch helpers ----------------------------------------------------

    def log_decisions_batch(
        self,
        decisions: Sequence[Dict[str, Any]],
    ) -> int:
        records: list[dict[str, Any]] = []
        for d in decisions:
            records.append({
                "kind": "decision",
                "symbol": str(d.get("symbol") or "").upper().strip(),
                "entry": d.get("entry"),
                "stop": d.get("stop"),
                "target": d.get("target"),
                "timestamp": d.get("timestamp", ""),
                "reasoning": d.get("reasoning", ""),
                "logged_at": _utc_now_iso(),
            })
        _write_jsonl_batch(self.decisions_path, records)
        return len(records)

    def log_trades_batch(
        self,
        trades: Sequence[Dict[str, Any]],
    ) -> int:
        records: list[dict[str, Any]] = []
        for t in trades:
            records.append({
                "kind": "trade",
                "entry_time": t.get("entry_time", ""),
                "exit_time": t.get("exit_time", ""),
                "entry_price": t.get("entry_price"),
                "exit_price": t.get("exit_price"),
                "pnl": t.get("pnl"),
                "r_multiple": t.get("r_multiple"),
                "logged_at": _utc_now_iso(),
            })
        _write_jsonl_batch(self.trades_path, records)
        return len(records)

    # -- Read helpers -----------------------------------------------------

    def read_decisions(self) -> List[Dict[str, Any]]:
        return read_jsonl(self.decisions_path)

    def read_orders(self) -> List[Dict[str, Any]]:
        return read_jsonl(self.orders_path)

    def read_trades(self) -> List[Dict[str, Any]]:
        return read_jsonl(self.trades_path)

    def read_validations(self) -> List[Dict[str, Any]]:
        return read_jsonl(self.validation_path)
