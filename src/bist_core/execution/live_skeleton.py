"""
FAZ76: Minimal live execute skeleton — BrokerAdapter (via ExecutionProvider), ledger, portfolio; idempotent.
Uses BrokerAdapter to place orders from orders_intent.json, records deterministic audit ledger,
updates portfolio accounting from fills. Re-running same day with same orders_intent does not duplicate.
No external libs.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from bist_core.audit.ledger import write_fills_jsonl, write_orders_jsonl, write_positions_jsonl
from bist_core.execution.result_writer import EXECUTION_RESULT_FILENAME, write_execution_result
from bist_core.portfolio.accounting import apply_fills, create_initial_state
from bist_core.reconciliation import write_reconciliation
from bist_core.services import snapshot_integrity
from bist_core.dossier.write import update_dossier_evidence

PORTFOLIO_STATE_FILENAME = "state.json"


def _orders_intent_sha256(path: Path) -> str:
    """Deterministic SHA256 hex of orders_intent file content."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_portfolio_state(state_path: Path) -> Dict[str, Any]:
    """Load portfolio state from JSON; if missing return create_initial_state(0)."""
    if not state_path.is_file():
        return create_initial_state(0.0)
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "cash" in data and "positions" in data:
            return data
    except (json.JSONDecodeError, TypeError, OSError):
        pass
    return create_initial_state(0.0)


def _save_portfolio_state(state_path: Path, state: Dict[str, Any]) -> None:
    """Write portfolio state JSON deterministically (sorted keys where applicable)."""
    state_path.parent.mkdir(parents=True, exist_ok=True)
    out = {
        "cash": state.get("cash", 0.0),
        "positions": dict(sorted((k, v) for k, v in (state.get("positions") or {}).items())),
        "realized_pnl": state.get("realized_pnl", 0.0),
        "turnover": state.get("turnover", 0.0),
    }
    snapshot_integrity.atomic_write_json(state_path, out)


def _state_to_positions(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Build positions list from state (sorted by symbol, non-zero qty only)."""
    positions = []
    for sym in sorted((state.get("positions") or {}).keys()):
        p = state["positions"][sym]
        qty = p.get("qty", 0.0)
        if qty != 0:
            positions.append({"symbol": sym, "qty": qty, "cost_basis": p.get("cost_basis", 0.0)})
    return positions


def run_live_execute_skeleton(
    outdir: Path | str,
    day: str,
    orders_intent_path: Path | str,
    execution_provider: Any,
    *,
    fee_bps: float = 0.0,
    slippage_bps: float = 0.0,
    initial_cash: float = 0.0,
    provider_name: str = "stub",
    execution_mode: str = "live",
) -> Tuple[bool, Optional[str]]:
    """
    Minimal live execute: place orders via provider (BrokerAdapter), write ledger, update portfolio. Idempotent.
    Returns (ok, error_msg). If error_msg set, ok is False. On success writes execution_result with orders_intent_sha256.
    """
    out_path = Path(outdir)
    day_str = str(day)
    intent_path = Path(orders_intent_path)
    if not intent_path.is_file():
        return (False, "orders_intent_not_found")
    intent_sha = _orders_intent_sha256(intent_path)
    day_dir = out_path / day_str
    exec_result_path = day_dir / "execution_result.json"
    ledger_fills_path = out_path / "ledger" / day_str / "fills.jsonl"

    # Idempotency: already executed this day with same orders_intent -> skip
    if exec_result_path.is_file() and ledger_fills_path.is_file():
        try:
            er = json.loads(exec_result_path.read_text(encoding="utf-8"))
            if er.get("ok") and er.get("orders_intent_sha256") == intent_sha:
                return (True, None)
        except (json.JSONDecodeError, TypeError, OSError):
            pass

    try:
        orders_intent = json.loads(intent_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, TypeError, OSError):
        return (False, "invalid_orders_intent")

    result = execution_provider.submit_orders(orders_intent, dry_run=False)
    if not result.get("ok", True):
        errs = result.get("errors") or []
        return (False, errs[0] if errs else "submit_orders_failed")

    fills = result.get("details", {}).get("fills") or []
    actions = orders_intent.get("actions") or []
    day_dir.mkdir(parents=True, exist_ok=True)

    # Ensure fills have "day" for deterministic sort
    for f in fills:
        if "day" not in f:
            f["day"] = day_str
    fills_sorted = sorted(fills, key=lambda x: (x.get("day", ""), x.get("symbol", "")))

    # Load portfolio state, apply fills, save
    portfolio_dir = out_path / "portfolio"
    state_path = portfolio_dir / PORTFOLIO_STATE_FILENAME
    state = _load_portfolio_state(state_path)
    apply_fills(state, fills_sorted, fee_bps=fee_bps, slippage_bps=slippage_bps, sort_key=None)
    _save_portfolio_state(state_path, state)
    positions = _state_to_positions(state)

    # Ledger: deterministic order
    write_orders_jsonl(out_path, day_str, actions)
    write_fills_jsonl(out_path, day_str, fills_sorted)
    write_positions_jsonl(out_path, day_str, positions)

    # orders_sent.json (same shape as before)
    snapshot_integrity.atomic_write_json(
        day_dir / "orders_sent.json",
        {"day": day_str, "actions": actions, **orders_intent},
    )
    write_execution_result(
        out_path,
        day_str,
        ok=True,
        blocked=False,
        reason="",
        provider=provider_name,
        mode=execution_mode,
        execution=execution_mode,
        orders_intent_sha256=intent_sha,
    )
    # FAZ77: reconciliation + link into dossier evidence
    ledger_dir = out_path / "ledger" / day_str
    fills_path = ledger_dir / "fills.jsonl"
    recon_path = write_reconciliation(out_path, day_str, intent_path, fills_path)
    exec_result_path = day_dir / EXECUTION_RESULT_FILENAME
    orders_ledger_path = ledger_dir / "orders.jsonl"
    positions_ledger_path = ledger_dir / "positions.jsonl"
    extra_evidence = {
        "reconciliation_path": str(recon_path),
        "execution_result_path": str(exec_result_path),
        "ledger_orders_path": str(orders_ledger_path),
        "ledger_fills_path": str(fills_path),
        "ledger_positions_path": str(positions_ledger_path),
    }
    update_dossier_evidence(out_path, day_str, extra_evidence)
    return (True, None)


__all__ = ["run_live_execute_skeleton", "PORTFOLIO_STATE_FILENAME"]
