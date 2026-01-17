from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

__all__ = [
    "DatasetMetadata",
    "DatasetRegistry",
    "get_default_registry",
    "register_dataset",
    "load_registered_dataset",
    "DEFAULT_REGISTRY_ENV",
    "DEFAULT_REGISTRY_RELATIVE",
]

DEFAULT_REGISTRY_ENV = "BIST_CORE_REGISTRY_PATH"
DEFAULT_REGISTRY_RELATIVE = ".bist_core/registry.json"


@dataclass
class DatasetMetadata:
    """
    Minimal dataset tanımı.

    name : Registry'deki isim (örn: 'eq_daily')
    kind : Veri tipi (örn: 'local_csv', ileride 'vendor_api' vs eklenebilir)
    path : Fiziksel root path (örn: '/data/bist/eq_daily')
    created_at : ISO8601 UTC timestamp
    updated_at : ISO8601 UTC timestamp
    """
    name: str
    kind: str
    path: str
    created_at: str
    updated_at: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "DatasetMetadata":
        return cls(**data)


class DatasetRegistry:
    """
    Basit JSON tabanlı kalıcı registry.

    Thread-safe / multi-process lock şimdilik yok; ileride eklenebilir.
    """

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path: Path = self._resolve_path(path)
        self._datasets: Dict[str, DatasetMetadata] = {}
        self._loaded: bool = False

    def _resolve_path(self, path: Optional[Path]) -> Path:
        if path is not None:
            return Path(path).expanduser()

        env_path = os.getenv(DEFAULT_REGISTRY_ENV)
        if env_path:
            return Path(env_path).expanduser()

        # default: ~/.bist_core/registry.json
        home = Path.home()
        return home / DEFAULT_REGISTRY_RELATIVE

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> None:
        if self._loaded:
            return

        if self._path.is_file():
            try:
                with self._path.open("r", encoding="utf-8") as f:
                    raw = json.load(f)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Registry JSON is invalid: {self._path}"
                ) from exc

            if not isinstance(raw, dict):
                raise ValueError(f"Registry JSON schema invalid: {self._path}")
            raw_datasets = raw.get("datasets")
            if not isinstance(raw_datasets, dict):
                raise ValueError(f"Registry JSON schema invalid: {self._path}")

            self._datasets = {
                name: DatasetMetadata.from_dict(meta)
                for name, meta in raw_datasets.items()
            }
        else:
            self._datasets = {}

        self._loaded = True

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "datasets": {
                name: meta.to_dict() for name, meta in sorted(self._datasets.items())
            },
        }
        tmp_path = self._path.with_suffix(self._path.suffix + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=True)
        tmp_path.replace(self._path)

    def list_datasets(self) -> List[str]:
        self.load()
        return sorted(self._datasets.keys())

    def get(self, name: str) -> DatasetMetadata:
        self.load()
        try:
            return self._datasets[name]
        except KeyError as exc:
            raise KeyError(f"Dataset not found in registry: {name!r}") from exc

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def register(
        self,
        name: str,
        kind: str,
        path: Path | str,
        overwrite: bool = False,
    ) -> DatasetMetadata:
        """
        Dataset kaydı oluşturur veya günceller.

        overwrite=False ise isim çakışmasında ValueError fırlatır.
        """
        self.load()
        path_str = str(Path(path).expanduser())
        now = self._now_iso()

        if name in self._datasets and not overwrite:
            raise ValueError(
                f"Dataset already exists in registry: {name!r}. "
                f"Use overwrite=True to update."
            )

        if name in self._datasets:
            meta = self._datasets[name]
            # created_at korunur, updated_at yenilenir
            meta.kind = kind
            meta.path = path_str
            meta.updated_at = now
        else:
            meta = DatasetMetadata(
                name=name,
                kind=kind,
                path=path_str,
                created_at=now,
                updated_at=now,
            )

        self._datasets[name] = meta
        self.save()
        return meta

    def remove(self, name: str) -> None:
        """
        Dataset'i registry'den siler. Diskteki veriye dokunmaz.
        """
        self.load()
        if name in self._datasets:
            del self._datasets[name]
            self.save()
        else:
            raise KeyError(f"Dataset not found in registry: {name!r}")


def get_default_registry(path: Optional[Path] = None) -> DatasetRegistry:
    """
    Library call'lar için kısayol.
    """
    return DatasetRegistry(path=path)


# ---- compatibility helper functions ----------------------------------------

def register_dataset(
    dataset_id: str,
    path: Path | str,
    *,
    kind: str = "local_csv",
    overwrite: bool = False,
    **meta: Any,
) -> DatasetMetadata:
    """
    Compatibility function for the old API.
    
    Registers a dataset using the default registry.
    Uses dataset_id as the name for backward compatibility.
    
    Args:
        dataset_id: Name of the dataset in the registry
        path: Root path to the dataset directory
        kind: Dataset kind (e.g., 'local_csv')
        overwrite: If True, allow overwriting existing dataset. Defaults to False
            for safety. Set to True explicitly to update existing entries.
        **meta: Additional metadata (currently unused, reserved for future use)
    
    Returns:
        DatasetMetadata for the registered dataset
        
    Raises:
        ValueError: If dataset already exists and overwrite=False
    """
    registry = get_default_registry()
    return registry.register(
        name=dataset_id,
        kind=kind,
        path=path,
        overwrite=overwrite,
    )


def load_registered_dataset(dataset_id: str) -> "pd.DataFrame":
    """
    Compatibility function for the old API.
    
    Loads a registered dataset as a pandas DataFrame.
    For local_csv kind, expects the path to be a directory containing CSV files.
    """
    import pandas as pd
    
    registry = get_default_registry()
    meta = registry.get(dataset_id)
    
    if meta.kind != "local_csv":
        raise ValueError(f"Unsupported dataset kind: {meta.kind!r}")
    
    root = Path(meta.path)
    csv_files = sorted(root.glob("*.csv"))
    if not csv_files:
        raise FileNotFoundError(f"No CSV files found under {root}")
    frames = [pd.read_csv(p) for p in csv_files]
    return pd.concat(frames, ignore_index=True)

