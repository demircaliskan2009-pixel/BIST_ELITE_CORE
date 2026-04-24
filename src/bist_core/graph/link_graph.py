"""
FAZ73: Link graph between knowledge docs <-> advice records <-> dossier evidence.
Stable ids; written under outdir/graph/<day>/links.json; deterministic ordering.
No external libs.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

LINK_GRAPH_SCHEMA_VERSION = 1
NODE_DOSSIER = "dossier"


def _stable_doc_id(entry: Dict[str, Any], fallback_line: str) -> str:
    """Stable id for a knowledge doc: entry['id'] or entry['doc_id'] or sha256(line)[:16]."""
    kid = entry.get("id") or entry.get("doc_id")
    if kid and isinstance(kid, str):
        return kid.strip()
    return hashlib.sha256(fallback_line.encode("utf-8")).hexdigest()[:16]


def _stable_advice_id(line: str) -> str:
    """Stable id for an advice record: sha256(canonical line)[:16]."""
    return hashlib.sha256(line.encode("utf-8")).hexdigest()[:16]


def _collect_knowledge_doc_ids(research_path: Optional[Path]) -> List[str]:
    """Read research entries.jsonl and return sorted list of stable doc ids."""
    if not research_path:
        return []
    path = Path(research_path) / "entries.jsonl" if research_path.is_dir() else research_path
    if not path.is_file():
        return []
    ids: List[str] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                kid = _stable_doc_id(entry, line)
                if kid:
                    ids.append(kid)
            except (json.JSONDecodeError, TypeError):
                continue
    return sorted(ids)


def _collect_advice_record_ids(advice_path: Optional[Path]) -> List[str]:
    """Read advice_records.jsonl and return sorted list of stable advice ids."""
    if not advice_path:
        return []
    path = Path(advice_path)
    if not path.is_file():
        return []
    ids: List[str] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            ids.append(_stable_advice_id(line))
    return sorted(ids)


def _collect_evidence_keys(dossier_json_path: Optional[Path]) -> List[str]:
    """Read dossier.json and return sorted list of evidence keys (from evidence object)."""
    if not dossier_json_path:
        return []
    path = Path(dossier_json_path)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        evidence = data.get("evidence")
        if isinstance(evidence, dict):
            return sorted(evidence.keys())
        return []
    except (json.JSONDecodeError, TypeError, OSError):
        return []


def write_link_graph(
    day: str,
    outdir: Path | str,
    *,
    research_path: Optional[Path | str] = None,
    advice_path: Optional[Path | str] = None,
    dossier_json_path: Optional[Path | str] = None,
) -> Path:
    """
    Build link graph (knowledge_docs <-> advice_records <-> dossier evidence) with stable ids
    and write outdir/graph/<day>/links.json. Deterministic ordering.
    Returns path to written links.json.
    """
    out_path = Path(outdir)
    day_str = str(day)
    graph_dir = out_path / "graph" / day_str
    graph_dir.mkdir(parents=True, exist_ok=True)
    out_file = graph_dir / "links.json"

    research_p = Path(research_path) if research_path else None
    advice_p = Path(advice_path) if advice_path else None
    dossier_p = Path(dossier_json_path) if dossier_json_path else None

    knowledge_doc_ids = _collect_knowledge_doc_ids(research_p)
    advice_record_ids = _collect_advice_record_ids(advice_p)
    evidence_keys = _collect_evidence_keys(dossier_p)
    dossier_path_str = str(dossier_p) if dossier_p else ""

    links: List[Dict[str, str]] = []
    for doc_id in knowledge_doc_ids:
        links.append({"from": doc_id, "to": "research_path", "type": "doc_to_evidence"})
    for aid in advice_record_ids:
        links.append({"from": aid, "to": "advice_path", "type": "advice_to_evidence"})
    for key in evidence_keys:
        links.append({"from": key, "to": NODE_DOSSIER, "type": "evidence_in_dossier"})

    links.sort(key=lambda x: (x["type"], x["from"], x["to"]))

    payload: Dict[str, Any] = {
        "schema_version": LINK_GRAPH_SCHEMA_VERSION,
        "day": day_str,
        "nodes": {
            "knowledge_docs": knowledge_doc_ids,
            "advice_records": advice_record_ids,
            "evidence": evidence_keys,
            "dossier": dossier_path_str,
        },
        "links": links,
    }

    tmp = out_file.with_name(out_file.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
    tmp.replace(out_file)
    return out_file


__all__ = ["write_link_graph", "LINK_GRAPH_SCHEMA_VERSION", "NODE_DOSSIER"]
