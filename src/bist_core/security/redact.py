"""
FAZ99: Recursive secrets redaction for artifacts (execution_result, dossier, reconciliation).
Key match (case-insensitive): secret, token, apikey, api_key, password, passwd, bearer, authorization, cookie, session.
Value replaced with ***REDACTED***. Raw secrets must not appear in json artifacts.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

REDACT_PLACEHOLDER = "***REDACTED***"

# Case-insensitive key patterns that indicate secret values
SECRET_KEY_PATTERN = re.compile(
    r"(secret|token|apikey|api_key|password|passwd|bearer|authorization|cookie|session)",
    re.IGNORECASE,
)


def _is_secret_key(key: str) -> bool:
    """True if key looks like a secret (case-insensitive match)."""
    return bool(SECRET_KEY_PATTERN.search(key))


def redact_recursive(obj: Any) -> Any:
    """
    Deep copy of obj with secret-like keys redacted (value -> ***REDACTED***).
    Recurses into dicts and lists. Does not mutate input.
    """
    if isinstance(obj, dict):
        out: Dict[str, Any] = {}
        for k, v in obj.items():
            if _is_secret_key(k) and v not in (None, ""):
                out[k] = REDACT_PLACEHOLDER
            else:
                out[k] = redact_recursive(v)
        return out
    if isinstance(obj, list):
        return [redact_recursive(item) for item in obj]
    return obj


__all__ = ["redact_recursive", "REDACT_PLACEHOLDER"]
