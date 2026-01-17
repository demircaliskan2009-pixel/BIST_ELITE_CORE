from __future__ import annotations

import json
from pathlib import Path

import pytest

from bist_core.data.registry import DatasetRegistry, DEFAULT_REGISTRY_RELATIVE


def _set_home(monkeypatch, tmp_path: Path) -> Path:
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setenv("HOME", str(home_dir))
    monkeypatch.setenv("USERPROFILE", str(home_dir))
    monkeypatch.delenv("BIST_CORE_REGISTRY_PATH", raising=False)
    return home_dir


def test_registry_persist_roundtrip(tmp_path: Path, monkeypatch) -> None:
    home_dir = _set_home(monkeypatch, tmp_path)
    registry_path = home_dir / DEFAULT_REGISTRY_RELATIVE

    reg1 = DatasetRegistry()
    meta1 = reg1.register(
        name="eq_daily",
        kind="local_csv",
        path=tmp_path / "eq_daily",
    )

    assert meta1.name == "eq_daily"
    assert meta1.kind == "local_csv"
    assert meta1.path.endswith("eq_daily")

    # Yeni instance aynı dosyadan okur mu?
    reg2 = DatasetRegistry()
    all_names = reg2.list_datasets()
    assert all_names == ["eq_daily"]

    meta2 = reg2.get("eq_daily")
    assert meta2.name == meta1.name
    assert meta2.kind == meta1.kind
    assert meta2.path == meta1.path
    assert meta2.created_at == meta1.created_at
    assert meta2.updated_at == meta1.updated_at

    # overwrite=False iken tekrar register ValueError atmalı
    reg3 = DatasetRegistry()
    try:
        reg3.register(name="eq_daily", kind="local_csv", path=".", overwrite=False)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError when overwriting without flag")

    # overwrite=True iken updated_at değişmeli
    reg3.register(
        name="eq_daily",
        kind="local_csv",
        path=tmp_path / "eq_daily2",
        overwrite=True,
    )
    meta3 = reg3.get("eq_daily")
    assert meta3.path.endswith("eq_daily2")
    assert meta3.created_at == meta1.created_at
    assert meta3.updated_at != meta1.updated_at

    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    assert payload.get("version") == 1
    assert "datasets" in payload


def test_registry_fail_closed_on_invalid_json(tmp_path: Path, monkeypatch) -> None:
    home_dir = _set_home(monkeypatch, tmp_path)
    registry_path = home_dir / DEFAULT_REGISTRY_RELATIVE
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text("{", encoding="utf-8")

    reg = DatasetRegistry()
    with pytest.raises(ValueError, match="Registry JSON is invalid"):
        reg.list_datasets()

    with pytest.raises(ValueError, match="Registry JSON is invalid"):
        reg.register(name="eq_daily", kind="local_csv", path=tmp_path)

    assert registry_path.read_text(encoding="utf-8") == "{"
