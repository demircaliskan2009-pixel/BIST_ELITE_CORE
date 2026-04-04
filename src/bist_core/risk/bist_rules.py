"""
FAZ57: Data-driven BIST risk gates (no hardcoded rule numbers).
Reads optional CSV/JSON for tick_size, price_bands, vbts/restrictions.
When live: if any input missing -> fail-closed (preflight).
Uses rulespack (tick_sizes, price_bands) and restrictions (vbts flags).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def preflight_for_live(
    rulespack_dir: Optional[Path] = None,
    restrictions_path: Optional[Path] = None,
) -> Tuple[bool, List[str]]:
    """
    Preflight BIST rule data for live execution. Fail-closed when any input missing.
    Returns (ok, errors). When ok is False, errors list reasons (e.g. bist_rules_tick_bands_missing, bist_rules_vbts_missing).
    """
    errors: List[str] = []
    from bist_core.risk.rulespack import get_rulespack_dir, load_rulespack
    from bist_core.risk.restrictions import get_restrictions_path, load_restrictions
    # FAZ57_REQUIRE_RESTRICTIONS_V4
    try:
        _rp = None if restrictions_path is None else Path(restrictions_path)
        if (_rp is None) or (not _rp.exists()):
            errors.append('bist_rules_vbts_missing')
    except Exception:
        errors.append('bist_rules_vbts_missing')

    rp_dir = Path(rulespack_dir) if rulespack_dir is not None else get_rulespack_dir()
    pack, _ = load_rulespack(rp_dir)
    tick_rows = pack.get("tick_sizes") or []
    band_rows = pack.get("price_bands") or []
    if not tick_rows or not band_rows:
        errors.append("bist_rules_tick_bands_missing")

    res_path = Path(restrictions_path) if restrictions_path is not None else get_restrictions_path()
    if res_path is None or not res_path.is_file():
        errors.append("bist_rules_vbts_missing")
    else:
        _, _ = load_restrictions(res_path)

    return (len(errors) == 0, sorted(errors))


def load_bist_rules(
    rulespack_dir: Optional[Path] = None,
    restrictions_path: Optional[Path] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], List[str]]:
    """
    Load rulespack + restrictions. Returns (rulespack, restrictions_state, provenance, errors).
    When files missing, returns empty state and non-empty errors (for fail-closed reporting).
    """
    from bist_core.risk.rulespack import get_rulespack_dir, load_rulespack
    from bist_core.risk.restrictions import get_restrictions_path, load_restrictions

    errors: List[str] = []
    provenance: Dict[str, Any] = {"rulespack_dir": "", "restrictions_path": ""}

    rp_dir = Path(rulespack_dir) if rulespack_dir is not None else get_rulespack_dir()
    pack, rp_prov = load_rulespack(rp_dir)
    provenance["rulespack_dir"] = str(rp_dir)
    provenance["rulespack"] = rp_prov

    res_path = Path(restrictions_path) if restrictions_path is not None else get_restrictions_path()
    if res_path is None or not res_path.is_file():
        state: Dict[str, Any] = {"blocked_symbols": [], "short_sale_ban": False}
        provenance["restrictions_path"] = ""
        errors.append("bist_rules_vbts_missing")
    else:
        state, res_prov = load_restrictions(res_path)
        provenance["restrictions_path"] = str(res_path)
        provenance["restrictions"] = res_prov

    if not (pack.get("tick_sizes") or []) or not (pack.get("price_bands") or []):
        errors.append("bist_rules_tick_bands_missing")

    return (pack, state, provenance, sorted(errors))


class BISTRules:
    """Session-level microstructure checks for paper/live gating (deterministic)."""

    def is_price_valid(self, price: float) -> bool:
        try:
            p = float(price)
        except (TypeError, ValueError):
            return False
        return p >= 1.0

    def is_liquid(self, bars: Any) -> bool:
        if not isinstance(bars, list) or len(bars) < 5:
            return False
        last = bars[-5:]
        vols: list[float] = []
        for b in last:
            try:
                v = getattr(b, "volume", None)
                if isinstance(v, (int, float)) and v >= 0:
                    vols.append(float(v))
            except Exception:
                return False
        if len(vols) != 5:
            return False
        avg_volume = sum(vols) / 5.0
        return avg_volume > 1_000_000

    def is_trade_allowed(self, price: float, prev_close: float) -> bool:
        try:
            p = float(price)
            pc = float(prev_close)
        except (TypeError, ValueError):
            return False
        if pc <= 0:
            return False
        upper = pc * 1.10
        lower = pc * 0.90
        return lower <= p <= upper


__all__ = [
    "BISTRules",
    "load_bist_rules",
    "preflight_for_live",
]
