from __future__ import annotations

from pathlib import Path

from bist_core.cli.main import main
from bist_core.data.registry import DatasetRegistry


def _write_sample_csv(tmp_path: Path) -> Path:
    csv_dir = tmp_path / "eq_daily"
    csv_dir.mkdir()
    csv_file = csv_dir / "sample.csv"
    csv_file.write_text(
        "symbol,date,close\nAAA,2025-01-01,10.0\nAAA,2025-01-02,10.5\n",
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
            "--id",
            "eq_daily",
            "--path",
            str(csv_dir),
            "--format",
            "csv",
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
            "--id",
            "eq_daily",
            "--head",
            "1",
        ]
    )
    assert rc == 0
    captured = capsys.readouterr()
    assert "id=eq_daily" in captured.out
    assert "format=csv" in captured.out
    assert "path=" in captured.out
    assert "loaded dataset 'eq_daily' with 2 rows, 3 columns" in captured.out

    # 3) load --use-snapshot --as-of
    rc = main(
        [
            "data",
            "snapshot",
            "--id",
            "eq_daily",
            "--day",
            "2025-01-02",
        ]
    )
    assert rc == 0
    captured = capsys.readouterr()
    assert "snapshot created at" in captured.out

    snapshot_path = snapshot_root / "2025-01-02" / "snapshot.csv"
    assert snapshot_path.exists()
    rows = list(snapshot_path.read_text(encoding="utf-8").splitlines())
    assert rows[0] == "symbol,close"
    assert rows[1:] == ["AAA,10.5"]
