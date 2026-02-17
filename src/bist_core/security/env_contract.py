"""
FAZ99: Env contract — BIST_* keys must be on whitelist; else BLOCK + env_contract_violation.
System env vars (PATH, PYTHONPATH, TEMP, etc.) are allowed; only BIST_* are checked.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple

# Allowed BIST_* env keys (single source of truth). Add any BIST_* used in codebase.
BIST_ALLOWED_ENV_KEYS = frozenset([
    "BIST_API_KEY",  # if ever used for logging redaction only
    "BIST_BROKER_CONFIG",
    "BIST_CORE_ALLOW_NETWORK",
    "BIST_CORE_CONFIG",
    "BIST_CORE_EVENTS_DIR",
    "BIST_CORE_HOME",
    "BIST_CORE_MODEL_PLUGIN",
    "BIST_CORE_POLICY_FILE",
    "BIST_CORE_REGISTRY_PATH",
    "BIST_CORE_RISK_RULES",
    "BIST_CORE_SNAPSHOT_DIR",
    "BIST_CORPORATE_ACTIONS_FILE",
    "BIST_DATA_DIR",
    "BIST_EOD_SNAPSHOT_DIR",
    "BIST_INSTRUMENT_MASTER",
    "BIST_KAP_BASE_URL",
    "BIST_KAP_CACHE_DIR",
    "BIST_KAP_CACHE_ONLY",
    "BIST_KAP_EVENTS_URL_TEMPLATE",
    "BIST_KAP_FIXTURE_PATH",
    "BIST_KAP_RAW_DIR",
    "BIST_RAW_DIR",
    "BIST_KAP_URL_TEMPLATE",
    "BIST_RESTRICTIONS_FILE",
    "BIST_RESEARCH_SOURCE",
    "BIST_RESEARCH_URL",
    "BIST_RULESPACK_DIR",
    "BIST_SAMPLES_DIR",
])

def validate_bist_env_whitelist() -> Tuple[bool, List[Dict[str, Any]]]:
    """
    Fail-closed: any BIST_* env key not in BIST_ALLOWED_ENV_KEYS -> violation.
    Returns (ok, errors). Each error: {"code": "env_contract_violation", "message": "...", "key": "BIST_..."}.
    """
    errors: List[Dict[str, Any]] = []
    for key in os.environ:
        if not key.upper().startswith("BIST_"):
            continue
        if key in BIST_ALLOWED_ENV_KEYS:
            continue
        errors.append({
            "code": "env_contract_violation",
            "message": f"BIST_* env key not on whitelist: {key}",
            "key": key,
        })
    return (len(errors) == 0, errors)


__all__ = ["validate_bist_env_whitelist", "BIST_ALLOWED_ENV_KEYS"]
