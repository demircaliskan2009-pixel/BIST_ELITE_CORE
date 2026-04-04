from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd


DEFAULT_HOME_ENV = "BIST_CORE_HOME"


def _get_bist_core_home() -> Path:
    env_home = os.getenv(DEFAULT_HOME_ENV)
    if env_home:
        return Path(env_home).expanduser()
    return Path.home() / ".bist_core"


def _default_registry_path() -> Path:
    return _get_bist_core_home() / "registry.json"


def _save_json_atomic(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, ensure_ascii=False, indent=2)
    fd, tmp_name = tempfile.mkstemp(
        prefix=path.name + ".",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(data)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        os.replace(tmp_name, path)
    finally:
        try:
            if os.path.exists(tmp_name):
                os.remove(tmp_name)
        except OSError:
            pass


@dataclass
class DatasetMetadata:
    name: str
    path: str
    kind: str = "local_csv"

    @classmethod
    def from_dict(cls, data: Dict[str, Any], name: Optional[str] = None) -> "DatasetMetadata":
        resolved_name = str(data.get("name") or name or "")
        resolved_path = str(data.get("path") or "")
        resolved_kind = str(data.get("kind") or data.get("type") or "local_csv")
        return cls(name=resolved_name, path=resolved_path, kind=resolved_kind)

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "path": self.path, "kind": self.kind}


class DatasetRegistry:
    def __init__(self, path: Optional[Path] = None) -> None:
        if path is None:
            env_path = os.getenv("BIST_CORE_REGISTRY_PATH")
            self._path = Path(env_path).expanduser() if env_path else _default_registry_path()
        else:
            self._path = path.expanduser()

        self._datasets: Dict[str, DatasetMetadata] = {}
        self._loaded = False

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> None:
        if self._loaded:
            return

        if self._path.is_file():
            with self._path.open("r", encoding="utf-8") as f:
                raw = json.load(f)

            # Eski format: {"ds": {...}}
            # Yeni format: {"version": 1, "datasets": {"ds": {...}}}
            if isinstance(raw, dict) and "datasets" not in raw and "version" not in raw:
                raw_datasets = raw
            else:
                raw_datasets = raw.get("datasets", {}) if isinstance(raw, dict) else {}

            self._datasets = {
                name: DatasetMetadata.from_dict(meta, name=name) for name, meta in (raw_datasets or {}).items()
            }
        else:
            self._datasets = {}

        self._loaded = True

    def save(self) -> None:
        payload = {
            "version": 1,
            "datasets": {name: meta.to_dict() for name, meta in sorted(self._datasets.items())},
        }
        _save_json_atomic(self._path, payload)

    def register(self, name: str, path: str, kind: str = "local_csv") -> None:
        self.load()
        self._datasets[name] = DatasetMetadata(
            name=name,
            path=str(Path(path).expanduser()),
            kind=kind,
        )

    def get(self, name: str) -> Optional[DatasetMetadata]:
        self.load()
        return self._datasets.get(name)

    def list_datasets(self) -> List[str]:
        self.load()
        return sorted(self._datasets.keys())


def get_default_registry() -> DatasetRegistry:
    env_path = os.getenv("BIST_CORE_REGISTRY_PATH")
    if env_path:
        return DatasetRegistry(Path(env_path).expanduser())
    return DatasetRegistry(_default_registry_path())


def load_registered_dataset(dataset_id: str, **kwargs: Any) -> "pd.DataFrame":
    import pandas as pd

    reg = get_default_registry()
    meta = reg.get(dataset_id)
    if meta is None:
        raise KeyError(f"Dataset not found in registry: {dataset_id!r}")

    if meta.kind != "local_csv":
        raise ValueError(f"Unsupported dataset kind: {meta.kind!r}")

    root = Path(meta.path)
    csv_files = sorted(root.glob("*.csv"))
    if not csv_files:
        raise FileNotFoundError(f"No CSV files found under {root}")

    frames = [pd.read_csv(p) for p in csv_files]
    return pd.concat(frames, ignore_index=True)


__all__ = [
    "DatasetMetadata",
    "DatasetRegistry",
    "get_default_registry",
    "load_registered_dataset",
]
