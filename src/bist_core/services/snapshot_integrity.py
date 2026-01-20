from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Dict


def compute_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def build_snapshot_hash_manifest(snapshot_csv_path: Path) -> Dict[str, object]:
    day = snapshot_csv_path.parent.name
    size = snapshot_csv_path.stat().st_size
    return {
        "schema_version": 1,
        "day": day,
        "snapshot_path": str(snapshot_csv_path),
        "sha256": compute_sha256(snapshot_csv_path),
        "bytes": int(size),
        "ts_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def atomic_write_json(path: Path, payload: dict) -> None:
    tmp = path.with_name(f"{path.name}.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    tmp.replace(path)
