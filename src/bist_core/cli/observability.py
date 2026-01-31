"""
FAZ64: Structured JSON logging helper + standard error taxonomy codes for CLI.
One JSON object per log line; no noisy prints when using err_struct for exits.
"""
from __future__ import annotations

import json
import sys
from typing import Any, Dict, Optional

# ---- Error taxonomy (stable codes for CLI / automation) ----
ERROR_CONFIG_MISSING = "CONFIG_MISSING"
ERROR_ENV_INVALID = "ENV_INVALID"
ERROR_SNAPSHOT_DIR_MISSING = "SNAPSHOT_DIR_MISSING"
ERROR_MANIFEST_MISSING = "MANIFEST_MISSING"
ERROR_ORDERS_INTENT_MISSING = "ORDERS_INTENT_MISSING"
ERROR_RISK_GATE_DENIED = "RISK_GATE_DENIED"
ERROR_EXECUTION_BLOCKED = "EXECUTION_BLOCKED"
ERROR_EXECUTION_FAILED = "EXECUTION_FAILED"
ERROR_ARGS_REQUIRED = "ARGS_REQUIRED"
ERROR_ARTIFACT_HASH_MISMATCH = "ARTIFACT_HASH_MISMATCH"
ERROR_REGISTRY_MISSING = "REGISTRY_MISSING"
ERROR_REPO_ROOT_MISSING = "REPO_ROOT_MISSING"
ERROR_CORE_JSON_MISSING = "CORE_JSON_MISSING"
ERROR_CONFIG_INVALID = "CONFIG_INVALID"


def log_struct(
    level: str,
    code: str,
    message: str,
    *,
    stream: Optional[Any] = None,
    **kwargs: Any,
) -> None:
    """
    Write one JSON line: {"level": level, "code": code, "message": message, **kwargs}.
    Default stream is stderr so stdout stays clean for JSON output.
    """
    out = stream if stream is not None else sys.stderr
    payload: Dict[str, Any] = {
        "level": level,
        "code": code,
        "message": message,
    }
    for k, v in kwargs.items():
        if v is not None:
            payload[k] = v
    line = json.dumps(payload, ensure_ascii=False) + "\n"
    out.write(line)
    out.flush()


def err_struct(code: str, message: str, **kwargs: Any) -> None:
    """Convenience: log_struct(level='error', code=code, message=message, **kwargs)."""
    log_struct("error", code, message, **kwargs)
