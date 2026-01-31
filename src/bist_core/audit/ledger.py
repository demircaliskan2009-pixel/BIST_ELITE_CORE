"""
FAZ56: Standardized audit ledger outputs.
Write JSONL: orders, fills, positions under outdir/ledger/<day>/.
Deterministic filenames: orders.jsonl, fills.jsonl, positions.jsonl.
Atomic writes (.tmp then replace). No new dependencies.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, List


def _audit_ledger_dir(outdir: Path | str, day: str) -> Path:
    """Return Path to outdir/ledger/<day>/ (deterministic)."""
    root = Path(outdir)
    return root / "ledger" / day


def _atomic_write_jsonl(path: Path, rows: List[dict]) -> None:
    """Write JSONL atomically: one JSON object per line; .tmp then replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False))
            f.write("\n")
    tmp.replace(path)


def write_orders_jsonl(outdir: Path | str, day: str, orders: List[dict]) -> Path:
    """
    Write outdir/ledger/<day>/orders.jsonl (one JSON object per order).
    Returns the path written.
    """
    root = Path(outdir)
    ledger_dir = _audit_ledger_dir(root, day)
    path = ledger_dir / "orders.jsonl"
    _atomic_write_jsonl(path, orders if orders is not None else [])
    return path


def write_fills_jsonl(outdir: Path | str, day: str, fills: List[dict]) -> Path:
    """
    Write outdir/ledger/<day>/fills.jsonl (one JSON object per fill).
    Returns the path written.
    """
    root = Path(outdir)
    ledger_dir = _audit_ledger_dir(root, day)
    path = ledger_dir / "fills.jsonl"
    _atomic_write_jsonl(path, fills if fills is not None else [])
    return path


def write_positions_jsonl(outdir: Path | str, day: str, positions: List[dict]) -> Path:
    """
    Write outdir/ledger/<day>/positions.jsonl (one JSON object per position).
    Returns the path written.
    """
    root = Path(outdir)
    ledger_dir = _audit_ledger_dir(root, day)
    path = ledger_dir / "positions.jsonl"
    _atomic_write_jsonl(path, positions if positions is not None else [])
    return path
