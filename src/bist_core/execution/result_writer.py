"""
FAZ75: Single ExecutionResult schema + writer for outdir/<day>/execution_result.json.
Used by live preflight and execute paths; deterministic; written on ALL exit (success and fail-closed).
No external libs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from bist_core.services import snapshot_integrity


EXECUTION_RESULT_SCHEMA_VERSION = 1
EXECUTION_RESULT_FILENAME = "execution_result.json"

# Stable JSON keys in order (for deterministic output)
EXECUTION_RESULT_KEYS = (
    "schema_version",
    "day",
    "ok",
    "blocked",
    "reason",
    "provider",
    "mode",
    "execution",
    "errors",
)


def _normalize_error_item(item: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
    """FAZ99: Normalize error to dict with at least 'code'. str -> {code}; dict -> {code, ...}."""
    if isinstance(item, str):
        return {"code": item}
    if isinstance(item, dict):
        code = item.get("code") or item.get("error_marker") or "unknown"
        out = dict(item)
        out["code"] = str(code)
        return out
    return {"code": "unknown"}


def build_execution_result_payload(
    day: str,
    ok: bool,
    blocked: bool,
    reason: str,
    provider: str,
    mode: str,
    errors: Optional[List[Union[str, Dict[str, Any]]]] = None,
    execution: Optional[str] = None,
    orders_intent_sha256: Optional[str] = None,
) -> Dict[str, Any]:
    """Build deterministic ExecutionResult dict. Errors[] normalized to {code, ...}; sorted by code. Optional orders_intent_sha256 for idempotency."""
    raw = errors if errors is not None else []
    err_list = [_normalize_error_item(e) for e in raw]
    err_list.sort(key=lambda x: x.get("code", ""))
    exec_val = execution if execution is not None else mode
    out = {
        "schema_version": EXECUTION_RESULT_SCHEMA_VERSION,
        "day": str(day),
        "ok": bool(ok),
        "blocked": bool(blocked),
        "reason": str(reason),
        "provider": str(provider),
        "mode": str(mode),
        "execution": str(exec_val),
        "errors": err_list,
    }
    if orders_intent_sha256 is not None:
        out["orders_intent_sha256"] = str(orders_intent_sha256)
    return out


def write_execution_result(
    outdir: Path | str,
    day: str,
    *,
    ok: bool,
    blocked: bool,
    reason: str,
    provider: str,
    mode: str,
    errors: Optional[List[Union[str, Dict[str, Any]]]] = None,
    execution: Optional[str] = None,
    orders_intent_sha256: Optional[str] = None,
) -> Path:
    """
    Write outdir/<day>/execution_result.json with deterministic payload.
    Ensures day dir exists. Call on ALL exit paths (success and every fail-closed).
    Optional orders_intent_sha256 for idempotency (FAZ76). Returns path to written file.
    """
    out_path = Path(outdir)
    day_dir = out_path / str(day)
    day_dir.mkdir(parents=True, exist_ok=True)
    payload = build_execution_result_payload(
        day=day,
        ok=ok,
        blocked=blocked,
        reason=reason,
        provider=provider,
        mode=mode,
        errors=errors,
        execution=execution,
        orders_intent_sha256=orders_intent_sha256,
    )
    from bist_core.security.redact import redact_recursive

    payload = redact_recursive(payload)
    out_file = day_dir / EXECUTION_RESULT_FILENAME
    snapshot_integrity.atomic_write_json(out_file, payload)
    return out_file


__all__ = [
    "EXECUTION_RESULT_SCHEMA_VERSION",
    "EXECUTION_RESULT_FILENAME",
    "EXECUTION_RESULT_KEYS",
    "build_execution_result_payload",
    "write_execution_result",
]
