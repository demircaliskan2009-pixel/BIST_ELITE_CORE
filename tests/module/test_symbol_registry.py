"""Tests for persistent Symbol Registry."""

from __future__ import annotations

from pathlib import Path

import pytest

from bist_core.registry import InvalidRegistryError, SymbolRegistry


def test_register_and_get(tmp_path: Path) -> None:
    """Register symbol and retrieve metadata."""
    path = tmp_path / "registry.json"
    reg = SymbolRegistry(str(path))
    reg.register("GARAN", {"sector": "banking", "lot": 1000})
    meta = reg.get("GARAN")
    assert meta["sector"] == "banking"
    assert meta["lot"] == 1000
    assert reg.get("garan") == meta


def test_duplicate_symbol_rejected(tmp_path: Path) -> None:
    """Duplicate symbol registration raises InvalidRegistryError."""
    path = tmp_path / "registry.json"
    reg = SymbolRegistry(str(path))
    reg.register("ASELS", {"sector": "tech"})
    with pytest.raises(InvalidRegistryError) as exc_info:
        reg.register("ASELS", {"sector": "other"})
    assert "duplicate" in str(exc_info.value).lower()


def test_list_sorted(tmp_path: Path) -> None:
    """list() returns sorted deterministic list."""
    path = tmp_path / "registry.json"
    reg = SymbolRegistry(str(path))
    reg.register("THYAO", {"sector": "airline"})
    reg.register("GARAN", {"sector": "banking"})
    reg.register("ASELS", {"sector": "tech"})
    symbols = reg.list()
    assert symbols == ["ASELS", "GARAN", "THYAO"]


def test_invalid_json_file(tmp_path: Path) -> None:
    """Corrupted/invalid JSON raises InvalidRegistryError."""
    path = tmp_path / "registry.json"
    path.write_text("{ invalid json }", encoding="utf-8")
    with pytest.raises(InvalidRegistryError) as exc_info:
        SymbolRegistry(str(path))
    assert "invalid" in str(exc_info.value).lower() or "json" in str(exc_info.value).lower()


def test_missing_symbol(tmp_path: Path) -> None:
    """get() raises InvalidRegistryError for missing symbol."""
    path = tmp_path / "registry.json"
    reg = SymbolRegistry(str(path))
    reg.register("GARAN", {"sector": "banking"})
    with pytest.raises(InvalidRegistryError) as exc_info:
        reg.get("NONEXISTENT")
    assert "missing" in str(exc_info.value).lower()


def test_deterministic_persistence(tmp_path: Path) -> None:
    """Same operations produce same file content; sorted keys."""
    path1 = tmp_path / "reg1.json"
    path2 = tmp_path / "reg2.json"
    reg1 = SymbolRegistry(str(path1))
    reg1.register("THYAO", {"sector": "airline"})
    reg1.register("GARAN", {"sector": "banking"})
    reg1.register("ASELS", {"sector": "tech"})
    content1 = path1.read_text(encoding="utf-8")

    reg2 = SymbolRegistry(str(path2))
    reg2.register("THYAO", {"sector": "airline"})
    reg2.register("GARAN", {"sector": "banking"})
    reg2.register("ASELS", {"sector": "tech"})
    content2 = path2.read_text(encoding="utf-8")

    assert content1 == content2
    assert '"ASELS"' in content1
    assert '"GARAN"' in content1
    assert '"THYAO"' in content1
