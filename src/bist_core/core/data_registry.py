# src/bist_core/core/data_registry.py

from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Mapping

import json
import pandas as pd


@dataclass
class DatasetRecord:
    dataset_id: str
    path: str
    kind: str = "local_csv"
    meta: Mapping[str, Any] | None = None


class DatasetRegistry:
    """
    Faz-3 / Adım-1 için basit dosya tabanlı registry.
    """

    def __init__(self, registry_path: Path | str | None = None) -> None:
        if registry_path is None:
            registry_path = Path.home() / ".bist_core" / "registry.json"
        self._path = Path(registry_path)
        self._records: Dict[str, DatasetRecord] = {}
        self._load()

    # ---- internal helpers -------------------------------------------------

    def _load(self) -> None:
        if not self._path.exists():
            self._records = {}
            return

        data = json.loads(self._path.read_text(encoding="utf-8"))
        self._records = {
            ds_id: DatasetRecord(dataset_id=ds_id, **payload)
            for ds_id, payload in data.items()
        }

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            ds_id: asdict(rec) for ds_id, rec in self._records.items()
        }
        self._path.write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    # ---- public API -------------------------------------------------------

    def register_dataset(
        self,
        dataset_id: str,
        path: Path | str,
        *,
        kind: str = "local_csv",
        **meta: Any,
    ) -> DatasetRecord:
        rec = DatasetRecord(
            dataset_id=dataset_id,
            path=str(path),
            kind=kind,
            meta=meta or None,
        )
        self._records[dataset_id] = rec
        self._save()
        return rec

    def list_datasets(self) -> Dict[str, DatasetRecord]:
        # kopya döndürüyoruz; dışarıdan değişmesin
        return dict(self._records)

    def load_registered_dataset(self, dataset_id: str) -> pd.DataFrame:
        try:
            rec = self._records[dataset_id]
        except KeyError:
            raise KeyError(f"Unknown dataset_id: {dataset_id!r}") from None

        if rec.kind != "local_csv":
            raise ValueError(f"Unsupported dataset kind: {rec.kind!r}")

        return pd.read_csv(rec.path)


# ---- module-level default registry ----------------------------------------

_default_registry: DatasetRegistry | None = None


def get_default_registry() -> DatasetRegistry:
    global _default_registry
    if _default_registry is None:
        _default_registry = DatasetRegistry()
    return _default_registry


def register_dataset(dataset_id: str, path: Path | str, **meta: Any) -> DatasetRecord:
    return get_default_registry().register_dataset(dataset_id, path, **meta)


def load_registered_dataset(dataset_id: str) -> pd.DataFrame:
    return get_default_registry().load_registered_dataset(dataset_id)
