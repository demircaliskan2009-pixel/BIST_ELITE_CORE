from __future__ import annotations

from pathlib import Path

from bist_core.cli import main
from bist_core.data.registry import DatasetRegistry


def _write_sample_csv(tmp_path: Path) -> Path:
    csv_dir = tmp_path / "eq_daily"
    csv_dir.mkdir()
    csv_file = csv_dir / "sample.csv"
    csv_file.write_text(
        "symbol,date,close\n"
        "AAA,2025-01-01,10.0\n"
        "AAA,2025-01-02,10.5\n",
        encoding="utf-8",
    )
    return csv_dir


def test_cli_data_register_and_load(tmp_path: Path, monkeypatch, capsys) -> None:
    # Registry path'i env ile override edelim
    registry_path = tmp_path / "registry.json"
    monkeypatch.setenv("BIST_CORE_REGISTRY_PATH", str(registry_path))

    # Snapshot root'u da bu test altına alalım
    snapshot_root = tmp_path / "snapshots"
    monkeypatch.setenv("BIST_CORE_SNAPSHOT_DIR", str(snapshot_root))

    csv_dir = _write_sample_csv(tmp_path)

    # 1) register
    rc = main(
        [
            "data",
            "register",
            "--name",
            "eq_daily",
            "--kind",
            "local_csv",
            "--path",
            str(csv_dir),
        ]
    )
    assert rc == 0

    # Registry gerçekten yazıldı mı?
    reg = DatasetRegistry()
    names = reg.list_datasets()
    assert names == ["eq_daily"]

    # 2) load (raw dataset)
    rc = main(
        [
            "data",
            "load",
            "--name",
            "eq_daily",
            "--head",
            "1",
        ]
    )
    assert rc == 0
    captured = capsys.readouterr()
    assert "loaded dataset 'eq_daily' with 2 rows, 3 columns" in captured.out

    # 3) load --use-snapshot --as-of
    rc = main(
        [
            "data",
            "load",
            "--name",
            "eq_daily",
            "--use-snapshot",
            "--as-of",
            "2025-01-02",
            "--head",
            "0",
        ]
    )
    assert rc == 0
    captured = capsys.readouterr()
    assert "loaded dataset 'eq_daily' with 2 rows, 3 columns" in captured.out

    # Snapshot dosyası oluşmuş olmalı
    snapshot_files = list(snapshot_root.rglob("*.csv"))
    assert snapshot_files, "No snapshot CSVs created"
