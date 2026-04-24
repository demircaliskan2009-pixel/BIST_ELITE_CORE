"""
FAZ86: Rulespack validator — tick/bands/vbts/restrictions required for live.
Returns (ok, errors[]). Errors are stable codes: bist_rules_tick_bands_missing, bist_rules_vbts_missing.
Deterministic: errors sorted. No external deps.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple


def validate_rulespack(
    rulespack_dir: Optional[Path | str] = None,
    restrictions_path: Optional[Path | str] = None,
) -> Tuple[bool, List[str]]:
    """
    Validate BIST rulespack (tick/bands) and restrictions (vbts) required for live execution.
    Returns (ok, errors). When ok is False, errors are sorted codes:
    - bist_rules_tick_bands_missing: rulespack dir missing or tick_sizes/price_bands empty
    - bist_rules_vbts_missing: restrictions path missing or not a file
    """
    errors: List[str] = []

    from bist_core.risk.restrictions import get_restrictions_path, load_restrictions
    from bist_core.risk.rulespack import get_rulespack_dir, load_rulespack

    rp_dir = Path(rulespack_dir) if rulespack_dir is not None else get_rulespack_dir()
    pack, _ = load_rulespack(rp_dir)
    tick_rows = pack.get("tick_sizes") or []
    band_rows = pack.get("price_bands") or []
    if not tick_rows or not band_rows:
        errors.append("bist_rules_tick_bands_missing")

    res_path = restrictions_path
    if res_path is None:
        res_path = get_restrictions_path()
    res_path = Path(res_path) if res_path is not None else None
    if res_path is None or not res_path.is_file():
        errors.append("bist_rules_vbts_missing")
    else:
        load_restrictions(res_path)

    return (len(errors) == 0, sorted(errors))


__all__ = ["validate_rulespack"]
