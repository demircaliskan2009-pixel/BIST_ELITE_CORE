"""PaperExecutionProvider: writes orders to outdir/<day>/orders_sent.json when not dry_run (stdlib, deterministic)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from bist_core.execution.base import execution_result
from bist_core.services import snapshot_integrity


class PaperExecutionProvider:
    """Writes orders to outdir/<day>/orders_sent.json when not dry_run; otherwise only returns result."""

    def __init__(self, outdir: Path | str, day: str) -> None:
        self._outdir = Path(outdir)
        self._day = str(day)

    def submit_orders(self, orders: Dict[str, Any], *, dry_run: bool = True) -> Dict[str, Any]:
        actions = orders.get("actions") or []
        sent = len(actions) if isinstance(actions, list) else 0
        if dry_run:
            return execution_result(
                ok=True,
                errors=[],
                broker="paper",
                sent=sent,
                details={"dry_run": True, "day": self._day},
            )
        target_dir = self._outdir / self._day
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / "orders_sent.json"
        snapshot_integrity.atomic_write_json(path, orders)
        return execution_result(
            ok=True,
            errors=[],
            broker="paper",
            sent=sent,
            details={"path": str(path), "day": self._day},
        )
