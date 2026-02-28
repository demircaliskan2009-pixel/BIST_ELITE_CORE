"""
FAZ85: Instrument master load path via env/arg.
Resolve path from BIST_INSTRUMENT_MASTER or explicit arg; delegate to services.instrument_master.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Set, Tuple


def resolve_instrument_master_path(arg_path: str | Path | None, env_key: str = "BIST_INSTRUMENT_MASTER") -> Path | None:
    """Return Path to instrument master CSV from arg or env; None if neither set or file missing."""
    if arg_path is not None:
        p = Path(arg_path)
        return p if p.is_file() else None
    raw = os.environ.get(env_key)
    if not raw:
        return None
    p = Path(raw)
    return p if p.is_file() else None


def load_instrument_master_from_path(
    path: Path | str,
) -> Tuple[Set[str], Dict[str, Any], Dict[str, str]]:
    """Load instrument master CSV; returns (symbols_set, meta, symbol_to_id). Delegates to services.instrument_master."""
    from bist_core.services import instrument_master as svc

    return svc.load_instrument_master(path)
