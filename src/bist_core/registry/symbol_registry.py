"""Persistent Symbol Registry — atomic writes, deterministic, fail-closed."""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict


def _safe_user_home() -> Path:
    try:
        return Path.home()
    except RuntimeError:
        return Path.cwd()


DEFAULT_REGISTRY_PATH = _safe_user_home() / ".bist_core" / "registry.json"


class InvalidRegistryError(Exception):
    """Raised when registry data is invalid, corrupted, or operation fails."""

    pass


def _write_atomic(path: Path, payload: Dict[str, Any]) -> None:
    """Write JSON to path atomically (temp file → rename)."""
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


def _read_safe(path: Path) -> Dict[str, Any]:
    """Read JSON from path; raise InvalidRegistryError on corruption."""
    if not path.exists():
        return {"symbols": {}}
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as e:
        raise InvalidRegistryError(f"cannot read registry: {e}") from e
    if not raw.strip():
        return {"symbols": {}}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise InvalidRegistryError(f"invalid JSON: {e}") from e
    if not isinstance(data, dict):
        raise InvalidRegistryError("registry must be a JSON object")
    if "symbols" not in data:
        return {"symbols": {}}
    if not isinstance(data["symbols"], dict):
        raise InvalidRegistryError("symbols must be a JSON object")
    return data


class SymbolRegistry:
    """Persistent symbol registry with atomic writes and deterministic behavior."""

    def __init__(self, registry_path: str | None = None) -> None:
        if registry_path is None:
            self._path = DEFAULT_REGISTRY_PATH
        else:
            self._path = Path(registry_path)
        self._data: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        """Load registry from disk."""
        self._data = _read_safe(self._path).get("symbols", {})
        if not isinstance(self._data, dict):
            raise InvalidRegistryError("symbols must be a JSON object")

    def _save(self) -> None:
        """Save registry to disk atomically."""
        payload = {"symbols": self._data}
        _write_atomic(self._path, payload)

    def register(self, symbol: str, meta: dict) -> None:
        """Register symbol with metadata. Symbols stored UPPERCASE. Duplicates rejected."""
        key = str(symbol).strip().upper()
        if not key:
            raise InvalidRegistryError("symbol cannot be empty")
        if key in self._data:
            raise InvalidRegistryError(f"duplicate symbol: {key!r}")
        self._data[key] = dict(meta)
        self._save()

    def get(self, symbol: str) -> dict:
        """Get metadata for symbol. Raises InvalidRegistryError if not found."""
        key = str(symbol).strip().upper()
        if key not in self._data:
            raise InvalidRegistryError(f"missing symbol: {key!r}")
        return dict(self._data[key])

    def list(self) -> list[str]:
        """Return sorted deterministic list of registered symbols."""
        return sorted(self._data.keys())
