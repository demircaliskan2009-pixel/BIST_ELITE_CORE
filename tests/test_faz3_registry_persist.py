from __future__ import annotations

from pathlib import Path

from bist_core.data.registry import DatasetRegistry


def test_registry_persist_roundtrip(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.json"

    reg1 = DatasetRegistry(path=registry_path)
    meta1 = reg1.register(
        name="eq_daily",
        kind="local_csv",
        path=tmp_path / "eq_daily",
    )

    assert meta1.name == "eq_daily"
    assert meta1.kind == "local_csv"
    assert meta1.path.endswith("eq_daily")

    # Yeni instance aynı dosyadan okur mu?
    reg2 = DatasetRegistry(path=registry_path)
    all_names = reg2.list_datasets()
    assert all_names == ["eq_daily"]

    meta2 = reg2.get("eq_daily")
    assert meta2.name == meta1.name
    assert meta2.kind == meta1.kind
    assert meta2.path == meta1.path
    assert meta2.created_at == meta1.created_at
    assert meta2.updated_at == meta1.updated_at

    # overwrite=False iken tekrar register ValueError atmalı
    reg3 = DatasetRegistry(path=registry_path)
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
