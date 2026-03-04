from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _to_int(x: Any) -> int:
    try:
        return int(x)
    except Exception:
        return 0


def _collect_stage_errors(stages: Any) -> Tuple[List[str], List[str]]:
    errors: List[str] = []
    codes: List[str] = []
    if not isinstance(stages, dict):
        return errors, codes

    for name, info in stages.items():
        if not isinstance(info, dict):
            continue
        e = _to_int(info.get("errors", 0))
        if e > 0:
            errors.append(f"stage_errors:{name}={e}")
            codes.append(f"stage_{name}_errors")

    if errors and "stage_errors" not in codes:
        codes.insert(0, "stage_errors")
    return errors, codes


def _blocked(code: str, msg: str) -> Dict[str, Any]:
    return {"ok": False, "blocked": True, "codes": [code], "errors": [msg]}


def run_all(
    orders_intent: Dict[str, Any],
    stages: Dict[str, Any],
    policy_ruleset: Any = None,
    rulespack: Any = None,
) -> Dict[str, Any]:
    # 1) stage errors => block
    stage_errors, stage_codes = _collect_stage_errors(stages)
    if stage_errors:
        return {
            "ok": False,
            "blocked": True,
            "codes": stage_codes,
            "errors": stage_errors,
        }

    # 2) actions must exist
    actions = (orders_intent or {}).get("actions") or []
    if not isinstance(actions, list) or len(actions) == 0:
        return _blocked("no_actions", "no_actions")

    # 3) rulespack must exist (env preferred)
    rp_dir: Path | None = None
    env_rp = os.environ.get("BIST_RULESPACK_DIR")
    if env_rp:
        rp_dir = Path(env_rp)
    elif rulespack is not None:
        rp_dir = Path(str(rulespack))

    if rp_dir is None:
        return _blocked("rulespack_missing", "rulespack_missing")

    missing = []
    for fname in ("tick_sizes.csv", "price_bands.csv"):
        if not (rp_dir / fname).is_file():
            missing.append(fname)
    if missing:
        return _blocked("rulespack_missing", f"rulespack_missing:{','.join(missing)}")

    # 4) restrictions file if specified must exist
    restr = os.environ.get("BIST_RESTRICTIONS_FILE")
    if restr and not Path(restr).is_file():
        return _blocked("restrictions_missing", "restrictions_file_missing")

    # 5) core config if specified must exist
    cfg = os.environ.get("BIST_CORE_CONFIG")
    if cfg and not Path(cfg).is_file():
        return _blocked("core_config_missing", "core_config_missing")

    return {"ok": True, "blocked": False, "codes": [], "errors": []}
