from __future__ import annotations

from pathlib import Path
import pytest

from bist_core.datasets.registry import DatasetRegistry


def test_registry_persist_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    reg_path = tmp_path / "registry.json"
    monkeypatch.setenv("BIST_CORE_REGISTRY_PATH", str(reg_path))

    data = tmp_path / "sample.csv"
    data.write_text("a,b\n1,2\n", encoding="utf-8")

    r1 = DatasetRegistry().load()
    rec = r1.register(name="sample", path=data, kind="csv", meta={"source": "test"})
    r1.save()

    r2 = DatasetRegistry().load()
    assert "sample" in r2.datasets
    rec2 = r2.get("sample")
    assert rec2.path == rec.path
    assert rec2.kind == "csv"
    assert rec2.sha256 == rec.sha256
    assert rec2.meta.get("source") == "test"


def test_registry_fail_closed_missing_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    reg_path = tmp_path / "registry.json"
    monkeypatch.setenv("BIST_CORE_REGISTRY_PATH", str(reg_path))

    r = DatasetRegistry().load()
    with pytest.raises(FileNotFoundError):
        r.register(name="x", path=tmp_path / "nope.csv")
