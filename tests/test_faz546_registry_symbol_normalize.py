"""FAZ546: Registry uses normalize_symbol; uppercase symbols; trim. Test-first."""

from __future__ import annotations

from pathlib import Path


from bist_core.data.registry import (
    load_registered_dataset,
    register_dataset,
)
from bist_core.symbol import normalize_symbol


def _set_registry_home(monkeypatch, tmp_path: Path) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("BIST_CORE_HOME", str(home))
    monkeypatch.delenv("BIST_CORE_REGISTRY_PATH", raising=False)
    return home


def test_faz546_registry_symbol_uppercase(tmp_path: Path, monkeypatch) -> None:
    """Loaded dataset symbol column is uppercased via normalize_symbol."""
    _set_registry_home(monkeypatch, tmp_path)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "a.csv").write_text("symbol,close,date\nthyao,100,2024-01-01\n", encoding="utf-8")
    register_dataset("ds1", path=data_dir, symbol_col="symbol", overwrite=True)

    df = load_registered_dataset("ds1")
    assert "symbol" in df.columns
    assert list(df["symbol"]) == ["THYAO"]


def test_faz546_registry_symbol_trim(tmp_path: Path, monkeypatch) -> None:
    """Loaded dataset symbol column is trimmed (spaces removed)."""
    _set_registry_home(monkeypatch, tmp_path)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "b.csv").write_text("symbol,close\n  akbnk  ,50.0\n", encoding="utf-8")
    register_dataset("ds2", path=data_dir, symbol_col="symbol", overwrite=True)

    df = load_registered_dataset("ds2")
    assert list(df["symbol"]) == ["AKBNK"]


def test_faz546_registry_same_symbol_same_normalized(tmp_path: Path, monkeypatch) -> None:
    """Same symbol string -> same normalized output (deterministic)."""
    _set_registry_home(monkeypatch, tmp_path)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "c.csv").write_text("symbol,close\n  xyz  ,10.0\n  xyz  ,11.0\n", encoding="utf-8")
    register_dataset("ds3", path=data_dir, symbol_col="symbol", overwrite=True)

    df = load_registered_dataset("ds3")
    syms = list(df["symbol"])
    assert syms == ["XYZ", "XYZ"]
    assert syms[0] == normalize_symbol("  xyz  ")
