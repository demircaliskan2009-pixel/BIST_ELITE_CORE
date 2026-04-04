"""FAZ548: Shared symbol normalization. Uppercase, trim, deterministic."""

from __future__ import annotations


def normalize_symbol(s: str) -> str:
    """
    Normalize symbol: strip, uppercase, remove BIST .E suffix.
    Deterministic: same input -> same output.
    """
    t = (s or "").strip().upper()
    if t.endswith(".E"):
        t = t[:-2]
    return t
