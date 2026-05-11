from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    import pandas as pd

    from bist_core.models.ohlcv import OHLCVBar


__all__ = [
    "DatasetMetadata",
    "DatasetRegistry",
    "get_default_registry",
    "register_dataset",
    "load_registered_dataset",
    "get_bist_core_home",
    "load_registry",
    "save_registry_atomic",
    "list_datasets",
    "get_dataset",
    "DEFAULT_REGISTRY_ENV",
    "DEFAULT_REGISTRY_RELATIVE",
    "DEFAULT_REGISTRY_PATH",
    "DEFAULT_HOME_ENV",
]

DEFAULT_REGISTRY_ENV = "BIST_CORE_REGISTRY_PATH"
DEFAULT_REGISTRY_RELATIVE = ".bist_core/registry.json"
DEFAULT_HOME_ENV = "BIST_CORE_HOME"


def _safe_user_home() -> Path:
    try:
        return Path.home()
    except RuntimeError:
        return Path.cwd()


DEFAULT_REGISTRY_PATH = _safe_user_home() / DEFAULT_REGISTRY_RELATIVE


def get_bist_core_home() -> Path:
    env_home = os.getenv(DEFAULT_HOME_ENV)
    if env_home:
        return Path(env_home).expanduser()
    return _safe_user_home() / ".bist_core"


def _save_json_atomic(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
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
        last_exc: Exception | None = None
        for attempt in range(12):
            try:
                os.replace(tmp_name, path)
                last_exc = None
                break
            except PermissionError as exc:
                last_exc = exc
                win_error = getattr(exc, "winerror", None)
                if win_error in (5, 32):
                    time.sleep(0.05 * (attempt + 1))
                    continue
                raise
        if last_exc is not None:
            raise last_exc
    finally:
        try:
            if os.path.exists(tmp_name):
                os.remove(tmp_name)
        except OSError:
            pass


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
    symbol_col: Optional[str] = None
    date_col: Optional[str] = None
    tz: Optional[str] = None

    def to_dict(self) -> dict:
        data = asdict(self)
        data["format"] = _format_from_kind(self.kind)
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "DatasetMetadata":
        fmt = str(data.get("format") or data.get("kind") or data.get("type") or "")
        kind = _kind_from_format(fmt)
        return cls(
            name=str(data.get("name") or ""),
            kind=kind,
            path=str(data.get("path") or ""),
            created_at=str(data.get("created_at") or ""),
            updated_at=str(data.get("updated_at") or ""),
            symbol_col=data.get("symbol_col"),
            date_col=data.get("date_col"),
            tz=data.get("tz"),
        )


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

        home = get_bist_core_home()
        return home / "registry.json"

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
                raise ValueError(f"Registry JSON is invalid: {self._path}") from exc

            if not isinstance(raw, dict):
                raise ValueError(f"Registry JSON schema invalid: {self._path}")
            raw_datasets = raw.get("datasets")
            if not isinstance(raw_datasets, dict):
                if "schema_version" not in raw and "version" not in raw:
                    raw_datasets = raw
                else:
                    raise ValueError(f"Registry JSON schema invalid: {self._path}")

            datasets: Dict[str, DatasetMetadata] = {}
            for name, meta in raw_datasets.items():
                if not isinstance(meta, dict):
                    continue
                datasets[name] = DatasetMetadata.from_dict({**meta, "name": name})
            self._datasets = datasets
        else:
            self._datasets = {}

        self._loaded = True

    def save(self) -> None:
        _save_json_atomic(self._path, self.to_payload())

    def list_datasets(self) -> List[str]:
        self.load()
        return sorted(self._datasets.keys())

    def get(self, name: str) -> DatasetMetadata:
        self.load()
        try:
            return self._datasets[name]
        except KeyError as exc:
            raise KeyError(f"Dataset not found in registry: {name!r}") from exc

    def to_payload(self) -> Dict[str, Any]:
        self.load()
        return _registry_payload(self._datasets)

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def register(
        self,
        name: str,
        kind: str,
        path: Path | str,
        symbol_col: Optional[str] = None,
        date_col: Optional[str] = None,
        tz: Optional[str] = None,
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
            raise ValueError(f"Dataset already exists in registry: {name!r}. Use overwrite=True to update.")

        if name in self._datasets:
            meta = self._datasets[name]
            # created_at korunur, updated_at yenilenir
            meta.kind = kind
            meta.path = path_str
            meta.symbol_col = symbol_col
            meta.date_col = date_col
            meta.tz = tz
            meta.updated_at = now
        else:
            meta = DatasetMetadata(
                name=name,
                kind=kind,
                path=path_str,
                created_at=now,
                updated_at=now,
                symbol_col=symbol_col,
                date_col=date_col,
                tz=tz,
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

    def get_ideal_chart_root(self) -> Optional[Path]:
        """
        First registered dataset with kind ideal_chart / ideal_intraday / ideal_binary.
        Path should be the IMKBH parent (e.g. ``C:\\...\\ChartData\\IMKBH``).
        """
        self.load()
        for meta in self._datasets.values():
            kind = str(getattr(meta, "kind", "") or "").lower()
            if kind in ("ideal_chart", "ideal_intraday", "ideal_binary"):
                return Path(meta.path).expanduser()
        return None

    def load_ideal_dataset(self, symbol: str, timeframe: str) -> "list[OHLCVBar]":
        """Load ``IMKBH'<symbol>.<tf>`` via :func:`bist_core.data.ideal_dataset.load_ideal_dataset`."""
        from bist_core.data.ideal_dataset import load_ideal_dataset as _load

        return _load(symbol, timeframe, registry=self)


def get_default_registry(path: Optional[Path] = None) -> DatasetRegistry:
    """
    Library call'lar için kısayol.
    """
    return DatasetRegistry(path=path)


def load_registry(path: Optional[Path] = None) -> DatasetRegistry:
    registry = DatasetRegistry(path=path)
    registry.load()
    return registry


def save_registry_atomic(registry: DatasetRegistry) -> None:
    registry.save()


def list_datasets(path: Optional[Path] = None) -> List[str]:
    return load_registry(path=path).list_datasets()


def get_dataset(name: str, path: Optional[Path] = None) -> DatasetMetadata:
    return load_registry(path=path).get(name)


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
        symbol_col=meta.get("symbol_col"),
        date_col=meta.get("date_col"),
        tz=meta.get("tz"),
        overwrite=overwrite,
    )


def load_registered_dataset(dataset_id: str) -> "pd.DataFrame":
    """
    Compatibility function for the old API.

    Loads a registered dataset as a pandas DataFrame.
    For local_csv kind, expects the path to be a directory containing CSV files.
    FAZ546: Symbol column (if present) is normalized via normalize_symbol (uppercase, trim).
    """
    import pandas as pd

    from bist_core.symbol import normalize_symbol

    registry = get_default_registry()
    meta = registry.get(dataset_id)

    if meta.kind != "local_csv":
        raise ValueError(f"Unsupported dataset kind: {meta.kind!r}")

    root = Path(meta.path)
    csv_files = sorted(root.glob("*.csv"))
    if not csv_files:
        raise FileNotFoundError(f"No CSV files found under {root}")
    frames = [pd.read_csv(p) for p in csv_files]
    df = pd.concat(frames, ignore_index=True)
    if meta.symbol_col and meta.symbol_col in df.columns:
        df[meta.symbol_col] = df[meta.symbol_col].astype(str).apply(normalize_symbol)
    return df


def _format_from_kind(kind: str) -> str:
    return "csv" if kind == "local_csv" else str(kind or "")


def _kind_from_format(value: str) -> str:
    fmt = (value or "").strip().lower()
    if fmt in ("csv", "local_csv"):
        return "local_csv"
    return fmt or "local_csv"


def _metadata_payload(meta: DatasetMetadata) -> Dict[str, Any]:
    data = meta.to_dict()
    optional_keys = ("symbol_col", "date_col", "tz")
    cleaned: Dict[str, Any] = {}
    for key in sorted(data.keys()):
        value = data[key]
        if key in optional_keys and value is None:
            continue
        cleaned[key] = value
    return cleaned


def _registry_payload(datasets: Dict[str, DatasetMetadata]) -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "version": 1,
        "datasets": {name: _metadata_payload(meta) for name, meta in sorted(datasets.items())},
    }
