"""Atomic JSONL research store in outdir/<day>/research/ (research_index.json + entries.jsonl)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def _stub_fetch_entries(day: str, source: str, offline: bool) -> List[Dict[str, Any]]:
    """Stub provider: returns 2 fake items; no network."""
    return [
        {"id": "stub_1", "day": day, "source": source, "title": "Fake research 1", "offline": offline},
        {"id": "stub_2", "day": day, "source": source, "title": "Fake research 2", "offline": offline},
    ]


def _fetch_entries_via_http(
    day: str,
    source: str,
    research_url: str,
    http_cache_dir: Path,
    offline: bool,
) -> List[Dict[str, Any]]:
    """FAZ67: Fetch research entries via offline-first HTTP cache. offline=True -> fixture mode (no network)."""
    from bist_core.http_cache import HttpClient

    client = HttpClient(
        cache_dir=http_cache_dir,
        ttl_seconds=3600,
        fixture_mode=offline,
    )
    resp, err = client.get(research_url)
    if err is not None:
        return [{"id": "http_error", "day": day, "source": source, "error_marker": err}]
    if resp is None:
        return [{"id": "http_miss", "day": day, "source": source, "error_marker": "cache_miss"}]
    body = resp.get("body") or b""
    try:
        raw = json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return [{"id": "http_parse_error", "day": day, "source": source, "error_marker": "invalid_json"}]
    if isinstance(raw, list):
        entries = []
        for i, item in enumerate(raw):
            if isinstance(item, dict):
                row = dict(item)
                row.setdefault("id", f"url_{i}")
                row.setdefault("day", day)
                row.setdefault("source", source)
                entries.append(row)
            else:
                entries.append({"id": f"url_{i}", "day": day, "source": source, "raw": str(item)})
        return entries if entries else [{"id": "url_empty", "day": day, "source": source}]
    if isinstance(raw, dict):
        raw.setdefault("id", "url_0")
        raw.setdefault("day", day)
        raw.setdefault("source", source)
        return [raw]
    return [{"id": "url_0", "day": day, "source": source, "raw": str(raw)}]


def _fetch_entries_via_kap_fixture(
    day: str,
    source: str,
    kap_fixture_path: Path,
) -> List[Dict[str, Any]]:
    """FAZ68: Ingest disclosures from KAP fixture HTML/JSON via connector; no network."""
    from bist_core.connectors.kap import ingest_from_html, ingest_from_json

    path = Path(kap_fixture_path)
    if not path.is_file():
        return [{"id": "kap_fixture_missing", "day": day, "source": source, "error_marker": "fixture_not_found"}]
    suffix = path.suffix.lower()
    if suffix == ".html":
        docs = ingest_from_html(path)
    elif suffix == ".json":
        docs = ingest_from_json(path)
    else:
        return [{"id": "kap_fixture_unsupported", "day": day, "source": source, "error_marker": "fixture_extension"}]
    entries: List[Dict[str, Any]] = []
    for doc in docs:
        published = (doc.get("published_at_utc") or "")[:10]
        entries.append(
            {
                "id": doc.get("doc_id", ""),
                "day": published or day,
                "source": doc.get("source", source),
                "title": doc.get("title", ""),
                "body": doc.get("body", ""),
                "tickers": doc.get("tickers", []),
                "published_at_utc": doc.get("published_at_utc", ""),
            }
        )
    return entries


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
    research_url: Optional[str] = None,
    http_cache_dir: Optional[Path | str] = None,
    kap_fixture_path: Optional[Path | str] = None,
) -> Dict[str, Any]:
    """
    Write research_index.json + entries.jsonl under outdir/<day>/research/.
    When source=='url' and research_url set, fetch via HTTP cache (offline=True -> fixture mode).
    When source=='kap' and kap_fixture_path set, ingest from fixture HTML/JSON via KAP connector (no network).
    Returns manifest dict: counts, errors, path, provenance (hash list).
    """
    out_path = Path(outdir)
    research_dir = out_path / day / "research"
    research_dir.mkdir(parents=True, exist_ok=True)

    if source == "url" and research_url and http_cache_dir is not None:
        cache_dir = Path(http_cache_dir)
        entries = _fetch_entries_via_http(day, source, research_url, cache_dir, offline)
        errors = [e.get("error_marker", "") for e in entries if e.get("error_marker")]
    elif source == "kap" and kap_fixture_path is not None:
        entries = _fetch_entries_via_kap_fixture(day, source, Path(kap_fixture_path))
        errors = [e.get("error_marker", "") for e in entries if e.get("error_marker")]
    else:
        entries = _stub_fetch_entries(day, source, offline)
        errors = []
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
