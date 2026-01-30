"""Atomic JSONL research store in outdir/<day>/research/ (research_index.json + entries.jsonl)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List


def _stub_fetch_entries(day: str, source: str, offline: bool) -> List[Dict[str, Any]]:
    """Stub provider: returns 2 fake items; no network."""
    return [
        {"id": "stub_1", "day": day, "source": source, "title": "Fake research 1", "offline": offline},
        {"id": "stub_2", "day": day, "source": source, "title": "Fake research 2", "offline": offline},
    ]


def _atomic_write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False))
            f.write("\n")
    tmp.replace(path)


def build_research_cache(
    day: str,
    outdir: Path | str,
    *,
    source: str = "kap",
    offline: bool = False,
) -> Dict[str, Any]:
    """
    Write research_index.json + entries.jsonl under outdir/<day>/research/.
    Deterministic paths. Returns manifest dict: counts, errors, path, provenance (hash list).
    """
    out_path = Path(outdir)
    research_dir = out_path / day / "research"
    research_dir.mkdir(parents=True, exist_ok=True)

    entries = _stub_fetch_entries(day, source, offline)
    errors: List[str] = []
    hashes: List[str] = []

    for ent in entries:
        line = json.dumps(ent, ensure_ascii=False, sort_keys=True)
        hashes.append(hashlib.sha256(line.encode("utf-8")).hexdigest()[:16])

    entries_path = research_dir / "entries.jsonl"
    _atomic_write_jsonl(entries_path, entries)

    index = {
        "schema_version": 1,
        "day": day,
        "source": source,
        "offline": offline,
        "count": len(entries),
        "errors": len(errors),
        "path": str(research_dir),
        "entries_path": str(entries_path),
        "provenance": sorted(hashes),
    }
    index_path = research_dir / "research_index.json"
    tmp_index = index_path.with_name(index_path.name + ".tmp")
    with tmp_index.open("w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    tmp_index.replace(index_path)

    return {
        "count": len(entries),
        "errors": len(errors),
        "path": str(research_dir),
        "provenance": sorted(hashes),
    }
