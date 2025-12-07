from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import pandas as pd
from .registry import DatasetRegistry, get_default_registry


__all__ = [
    "DEFAULT_SNAPSHOT_ENV",
    "DEFAULT_SNAPSHOT_RELATIVE",
    "get_default_snapshot_root",
    "build_snapshot_path",
    "write_eod_snapshot",
    "read_eod_snapshot",
    "build_and_store_eod_snapshot",
]

DEFAULT_SNAPSHOT_ENV = "BIST_CORE_SNAPSHOT_DIR"
DEFAULT_SNAPSHOT_RELATIVE = ".bist_core/eod/snapshots"


def get_default_snapshot_root(path: Optional[Path] = None) -> Path:
    """
    Snapshot root path'ini çözer.

    Öncelik:
      1) Fonksiyon parametresi
      2) Env: BIST_CORE_SNAPSHOT_DIR
      3) ~/.bist_core/eod/snapshots
    """
    if path is not None:
        return Path(path).expanduser()

    env_path = os.getenv(DEFAULT_SNAPSHOT_ENV)
    if env_path:
        return Path(env_path).expanduser()

    home = Path.home()
    return home / DEFAULT_SNAPSHOT_RELATIVE


def _normalize_as_of(as_of: date | str) -> date:
    if isinstance(as_of, date):
        return as_of
    # "YYYY-MM-DD" ⇒ date
    return datetime.strptime(as_of, "%Y-%m-%d").date()


def build_snapshot_path(
    root: Path,
    dataset_name: str,
    as_of: date | str,
    suffix: str = ".csv",
) -> Path:
    as_of_date = _normalize_as_of(as_of)
    ds_dir = root / dataset_name
    filename = f"{as_of_date.isoformat()}{suffix}"
    return ds_dir / filename


def write_eod_snapshot(
    df: "pd.DataFrame",
    root: Path,
    dataset_name: str,
    as_of: date | str,
) -> Path:
    """
    EOD snapshot'ı CSV olarak yazar ve path döner.
    """
    root = Path(root).expanduser()
    path = build_snapshot_path(root, dataset_name, as_of)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    return path


def read_eod_snapshot(
    root: Path,
    dataset_name: str,
    as_of: date | str,
) -> "pd.DataFrame":
    path = build_snapshot_path(root, dataset_name, as_of)
    if not path.is_file():
        raise FileNotFoundError(f"EOD snapshot not found: {path}")
    return pd.read_csv(path)


def _load_dataset_from_metadata(meta) -> "pd.DataFrame":
    """
    Şimdilik sadece kind == 'local_csv' için basit loader.
    İleride ingest.local_csv'i direkt kullanacak şekilde refactor edebiliriz.
    """
    root = Path(meta.path)
    if meta.kind == "local_csv":
        csv_files = sorted(root.glob("*.csv"))
        if not csv_files:
            raise FileNotFoundError(f"No CSV files found under {root}")
        frames = [pd.read_csv(p) for p in csv_files]
        return pd.concat(frames, ignore_index=True)
    raise ValueError(f"Unsupported dataset kind for EOD snapshot: {meta.kind!r}")


def build_and_store_eod_snapshot(
    dataset_name: str,
    as_of: date | str,
    registry: Optional[DatasetRegistry] = None,
    snapshot_root: Optional[Path] = None,
) -> Path:
    """
    Registry'den dataset'i bulur, veriyi yükler ve EOD snapshot yazar.
    """
    if registry is None:
        registry = get_default_registry()

    snapshot_root = get_default_snapshot_root(snapshot_root)
    meta = registry.get(dataset_name)
    df = _load_dataset_from_metadata(meta)
    return write_eod_snapshot(df, snapshot_root, dataset_name, as_of)
