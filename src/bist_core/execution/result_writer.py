"""
FAZ75: Single ExecutionResult schema + writer for outdir/<day>/execution_result.json.
Used by live preflight and execute paths; deterministic; written on ALL exit (success and fail-closed).
No external libs.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

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


def build_execution_result_payload(
    day: str,
    ok: bool,
    blocked: bool,
    reason: str,
    provider: str,
    mode: str,
    errors: Optional[List[str]] = None,
    execution: Optional[str] = None,
) -> Dict[str, Any]:
    """Build deterministic ExecutionResult dict. Errors are sorted. All keys always present."""
    err_list = sorted(errors) if errors is not None else []
    exec_val = execution if execution is not None else mode
    return {
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


def write_execution_result(
    outdir: Path | str,
    day: str,
    *,
    ok: bool,
    blocked: bool,
    reason: str,
    provider: str,
    mode: str,
    errors: Optional[List[str]] = None,
    execution: Optional[str] = None,
) -> Path:
    """
    Write outdir/<day>/execution_result.json with deterministic payload.
    Ensures day dir exists. Call on ALL exit paths (success and every fail-closed).
    Returns path to written file.
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
    )
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
