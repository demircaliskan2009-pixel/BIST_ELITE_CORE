from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

REGISTRY_SCHEMA_VERSION = 1

def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def default_registry_path() -> Path:
    """
    Default registry location (override with BIST_CORE_REGISTRY_PATH).
    Windows: C:\\Users\\<you>\\.bist_core\\registry.json
    """
    env = os.environ.get("BIST_CORE_REGISTRY_PATH")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".bist_core" / "registry.json"

def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

@dataclass(frozen=True)
class DatasetRecord:
    name: str
    path: str
    kind: str = "csv"
    created_at: str = ""
    sha256: str = ""
    meta: Dict[str, Any] = None  # type: ignore[assignment]

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if d["meta"] is None:
            d["meta"] = {}
        return d

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "DatasetRecord":
        return DatasetRecord(
            name=str(d.get("name", "")),
            path=str(d.get("path", "")),
            kind=str(d.get("kind", "csv")),
            created_at=str(d.get("created_at", "")),
            sha256=str(d.get("sha256", "")),
            meta=dict(d.get("meta") or {}),
        )

class DatasetRegistry:
    """
    Fail-closed dataset registry with on-disk persistence (JSON).

    Design goals:
    - Never silently accept missing files during registration.
    - Deterministic JSON output (sorted keys, stable formatting).
    - Explicit schema_version for forward compatibility.
    """
    def __init__(self, registry_path: Optional[Path] = None) -> None:
        self.registry_path = Path(registry_path) if registry_path is not None else default_registry_path()
        self._datasets: Dict[str, DatasetRecord] = {}

    @property
    def datasets(self) -> Dict[str, DatasetRecord]:
        return dict(self._datasets)

    def load(self) -> "DatasetRegistry":
        p = self.registry_path
        if not p.exists():
            self._datasets = {}
            return self

        raw = json.loads(p.read_text(encoding="utf-8"))
        if int(raw.get("schema_version", 0)) != REGISTRY_SCHEMA_VERSION:
            raise ValueError(f"Unsupported registry schema_version: {raw.get('schema_version')}")

        ds = raw.get("datasets") or {}
        out: Dict[str, DatasetRecord] = {}
        for k, v in ds.items():
            rec = DatasetRecord.from_dict(v)
            if not rec.name:
                rec = DatasetRecord.from_dict({**v, "name": k})
            out[rec.name] = rec

        self._datasets = out
        return self

    def save(self) -> None:
        p = self.registry_path
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": REGISTRY_SCHEMA_VERSION,
            "saved_at": _utcnow_iso(),
            "datasets": {name: rec.to_dict() for name, rec in sorted(self._datasets.items())},
        }
        p.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def register(
        self,
        *,
        name: str,
        path: Path,
        kind: str = "csv",
        meta: Optional[Dict[str, Any]] = None,
        allow_update: bool = False,
    ) -> DatasetRecord:
        if not name or not name.strip():
            raise ValueError("name required")

        p = Path(path).expanduser()
        if not p.exists():
            raise FileNotFoundError(str(p))

        if (not allow_update) and (name in self._datasets):
            raise ValueError(f"dataset already exists: {name}")

        rec = DatasetRecord(
            name=name,
            path=str(p),
            kind=kind,
            created_at=_utcnow_iso(),
            sha256=_sha256_file(p),
            meta=dict(meta or {}),
        )
        self._datasets[name] = rec
        return rec

    def get(self, name: str) -> DatasetRecord:
        if name not in self._datasets:
            raise KeyError(name)
        return self._datasets[name]

    def list_names(self) -> list[str]:
        return sorted(self._datasets.keys())

    def resolve_path(self, name: str) -> Path:
        return Path(self.get(name).path)
