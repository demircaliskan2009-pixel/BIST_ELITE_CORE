"""
FAZ90: Explainability — reasons[] and evidence_refs[] for advisory decisions.
Output: explain.json (deterministic). Linked from dossier evidence.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

EXPLAIN_SCHEMA_VERSION = 1


def build_explain(reasons: List[str], evidence_refs: List[str]) -> Dict[str, Any]:
    """
    Build deterministic explanation dict from reasons and evidence references.
    Returns dict suitable for explain.json: schema_version, reasons (sorted), evidence_refs (sorted).
    """
    reasons_sorted = sorted(str(r).strip() for r in (reasons or []) if str(r).strip())
    refs_sorted = sorted(str(r).strip() for r in (evidence_refs or []) if str(r).strip())
    return {
        "schema_version": EXPLAIN_SCHEMA_VERSION,
        "reasons": reasons_sorted,
        "evidence_refs": refs_sorted,
    }


def write_explain(path: Path | str, explain_data: Dict[str, Any]) -> Path:
    """Write explain.json with deterministic JSON (sort_keys, indent)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(explain_data, f, ensure_ascii=False, indent=2, sort_keys=True)
    tmp.replace(p)
    return p


__all__ = ["EXPLAIN_SCHEMA_VERSION", "build_explain", "write_explain"]
