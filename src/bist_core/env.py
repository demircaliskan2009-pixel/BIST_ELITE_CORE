"""
FAZ99: Env contract validator + secrets redaction.
validate_env_contract(required[]) -> (ok, errors[] with code).
redact_secrets: mask secret-like env values for safe logging.
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Tuple

REDACT_PLACEHOLDER = "***"

# Env key patterns that indicate secret values (case-insensitive)
SECRET_KEY_PATTERN = re.compile(
    r"(key|secret|token|password|auth|credential)",
    re.IGNORECASE,
)


def validate_env_contract(required: List[str]) -> Tuple[bool, List[Dict[str, Any]]]:
    """
    Validate that required env vars are set and non-empty.
    Returns (ok, errors). Each error: {"code": "env_missing_<VAR>", "message": "<VAR> not set"}.
    """
    errors: List[Dict[str, Any]] = []
    for var in required:
        if not var or not isinstance(var, str):
            continue
        value = os.environ.get(var)
        if value is None or (isinstance(value, str) and not value.strip()):
            code = f"env_missing_{var}"
            errors.append({"code": code, "message": f"{var} not set or empty"})
    return (len(errors) == 0, errors)


def _is_secret_key(key: str) -> bool:
    """True if key looks like a secret (e.g. BIST_API_KEY, BIST_SECRET)."""
    return bool(SECRET_KEY_PATTERN.search(key))


def redact_env(env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """
    Return a copy of env (or os.environ) with secret-like values redacted.
    Keys matching secret pattern (key, secret, token, password, etc.) get value "***".
    """
    source = dict(env) if env is not None else dict(os.environ)
    out: Dict[str, str] = {}
    for k, v in source.items():
        if v is None:
            out[k] = ""
            continue
        s = str(v).strip()
        if _is_secret_key(k) and s:
            out[k] = REDACT_PLACEHOLDER
        else:
            out[k] = s
    return out


def redact_secrets(payload: Dict[str, Any], keys_to_redact: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Return a copy of payload with secret-like keys redacted (value -> "***").
    If keys_to_redact is given, only those keys are redacted; else any key matching secret pattern.
    """
    out: Dict[str, Any] = {}
    for k, v in payload.items():
        if keys_to_redact is not None:
            if k in keys_to_redact and v not in (None, ""):
                out[k] = REDACT_PLACEHOLDER
            else:
                out[k] = v
        else:
            if _is_secret_key(k) and v not in (None, ""):
                out[k] = REDACT_PLACEHOLDER
            else:
                out[k] = v
    return out


__all__ = ["validate_env_contract", "redact_env", "redact_secrets", "REDACT_PLACEHOLDER"]
