"""
FAZ60: Dossier writer linking advice + research + risk decisions.
Writes outdir/dossier/<day>/dossier.json with stable ordering and evidence pointers (paths + hashes).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def _file_hash(path: Path) -> Optional[str]:
    """Return sha256 of file if exists, else None."""
    if not path.is_file():
        return None
    try:
        from bist_core.services import snapshot_integrity
        return snapshot_integrity.compute_sha256(path)
    except Exception:
        return None


def _stable_payload(evidence: Dict[str, Any]) -> Dict[str, Any]:
    """Build payload with stable key order and sorted lists for deterministic JSON."""
    out: Dict[str, Any] = {}
    for k in sorted(evidence.keys()):
        v = evidence[k]
        if v is None:
            continue
        if isinstance(v, list):
            v = sorted(v) if v and not isinstance(v[0], dict) else v
        out[k] = v
    return out


def write_dossier(
    day: str,
    outdir: Path | str,
    evidence: Dict[str, Any],
    *,
    dossier_path_key: str = "dossier_json_path",
) -> Path:
    """
    Write outdir/dossier/<day>/dossier.json with stable ordering.
    evidence: dict with keys such as advice_path, research_path, orders_intent_path,
              dossier_path (per-symbol dossiers dir), snapshot_hash, risk_notes, etc.
              Paths can be str or Path; hashes added for existing files when not provided.
    Returns path to written dossier.json.
    """
    out_path = Path(outdir)
    day_dir = out_path / "dossier" / day
    day_dir.mkdir(parents=True, exist_ok=True)
    out_file = day_dir / "dossier.json"

    payload: Dict[str, Any] = {
        "schema_version": 1,
        "day": day,
    }
    pointers: Dict[str, Any] = {}

    if evidence.get("advice_path"):
        p = Path(evidence["advice_path"])
        pointers["advice_path"] = str(p)
        if p.is_file() and not evidence.get("advice_sha256"):
            h = _file_hash(p)
            if h:
                pointers["advice_sha256"] = h
        elif evidence.get("advice_sha256"):
            pointers["advice_sha256"] = evidence["advice_sha256"]

    if evidence.get("research_path"):
        pointers["research_path"] = str(evidence["research_path"])

    if evidence.get("orders_intent_path"):
        p = Path(evidence["orders_intent_path"])
        pointers["orders_intent_path"] = str(p)
        if p.is_file() and not evidence.get("orders_intent_sha256"):
            h = _file_hash(p)
            if h:
                pointers["orders_intent_sha256"] = h
        elif evidence.get("orders_intent_sha256"):
            pointers["orders_intent_sha256"] = evidence["orders_intent_sha256"]

    if evidence.get("dossier_path"):
        pointers["dossier_path"] = str(evidence["dossier_path"])

    if evidence.get("snapshot_hash"):
        h = evidence["snapshot_hash"]
        if isinstance(h, dict):
            pointers["snapshot_sha256"] = h.get("value") or h.get("sha256") or ""
        else:
            pointers["snapshot_sha256"] = str(h)

    if evidence.get("restrictions"):
        r = evidence["restrictions"]
        if isinstance(r, dict):
            pointers["restrictions_file"] = r.get("file", "")
            pointers["restrictions_sha256"] = r.get("sha256", "")
        else:
            pointers["restrictions_file"] = str(r)

    if evidence.get("risk_notes"):
        notes = evidence["risk_notes"]
        pointers["risk_notes"] = sorted(notes) if isinstance(notes, list) else [str(notes)]

    if evidence.get("risk_allowed") is not None:
        payload["risk_allowed"] = bool(evidence["risk_allowed"])

    payload["evidence"] = _stable_payload(pointers)
    payload["dossier_json_path"] = str(out_file)

    stable = _stable_payload(payload)
    tmp = out_file.with_name(out_file.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(stable, f, ensure_ascii=False, indent=2, sort_keys=True)
    tmp.replace(out_file)
    return out_file
