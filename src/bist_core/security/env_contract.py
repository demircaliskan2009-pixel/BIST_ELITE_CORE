"""
FAZ99: Env contract — BIST_* keys must be on whitelist; else BLOCK + env_contract_violation.
System env vars (PATH, PYTHONPATH, TEMP, etc.) are allowed; only BIST_* are checked.

Windows note:
Environment variable names are case-insensitive; subprocess/env merges may preserve a different casing
(e.g. 'Bist_Core_Config'). Therefore whitelist matching MUST be case-insensitive.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Mapping, Tuple

# Allowed BIST_* env keys (single source of truth). Add any BIST_* used in codebase.
BIST_ALLOWED_ENV_KEYS = frozenset(
    [
        "BIST_API_KEY",  # if ever used for logging redaction only
        "BIST_ATR_N",  # FAZ585: Risk sizer ATR period
        "BIST_CAPITAL_TRY",  # FAZ585: Risk sizer capital
        "BIST_BROKER_CONFIG",
        "BIST_EXEC_PROVIDER",  # FAZ580: dry_run | real_skeleton
        "BIST_CORE_ALLOW_NETWORK",
        "BIST_CORE_CONFIG",
        "BIST_CORE_EVENTS_DIR",
        "BIST_CORE_HOME",
        "BIST_CORE_MODEL_PLUGIN",
        "BIST_CORE_POLICY_FILE",
        "BIST_CORE_REGISTRY_PATH",
        "BIST_CORE_STRATEGY_LOG",
        "BIST_CORE_STRATEGY_OUTCOMES",
        "BIST_CORE_OUTCOME_MAX_HOLD_DAYS",
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
        "BIST_RISK_PCT",  # FAZ585: Risk sizer risk %
        "BIST_STOP_ATR_MULT",  # FAZ585: Risk sizer stop distance multiplier
        "BIST_TP_R_MULT",  # FAZ585: Risk sizer take-profit R multiplier
        "BIST_RESEARCH_URL",
        "BIST_RULESPACK_DIR",
        "BIST_SAMPLES_DIR",
    ]
)


def validate_bist_env_whitelist(environ: Mapping[str, str] | None = None) -> Tuple[bool, List[Dict[str, Any]]]:
    """
    Fail-closed: any BIST_* env key not in BIST_ALLOWED_ENV_KEYS -> violation.

    Returns:
      (ok, errors)
      errors: [{"code":"env_contract_violation","message":"...","key":"BIST_..."}]
    """
    env = environ or os.environ

    allow_upper = {k.upper() for k in BIST_ALLOWED_ENV_KEYS}

    bad: List[str] = []
    for key in env.keys():
        ku = str(key).upper()
        if not ku.startswith("BIST_"):
            continue
        if ku in allow_upper:
            continue
        bad.append(str(key))

    if not bad:
        return True, []

    bad_sorted = sorted(set(bad), key=lambda s: s.upper())
    errors: List[Dict[str, Any]] = [
        {
            "code": "env_contract_violation",
            "message": "BIST_* env key(s) not on whitelist",
            "key": k,
        }
        for k in bad_sorted
    ]
    return False, errors


__all__ = ["validate_bist_env_whitelist", "BIST_ALLOWED_ENV_KEYS"]
