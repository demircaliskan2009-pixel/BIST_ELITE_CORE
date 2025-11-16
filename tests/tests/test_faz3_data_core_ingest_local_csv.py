import csv
import pytest
from bist_core.data.ingest import read_csv, register_dataset, load_registered_dataset
# tests/test_faz3_data_core_ingest_local_csv.py
from __future__ import annotations

from pathlib import Path
from bist_core.data import (
    DatasetSpec,
    register_dataset,
    load_registered_dataset,
    load_csv,
)


def _write_sample_csv(base: Path) -> Path:
    path = base / "eod" / "quotes.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "symbol,date,close,volume\n"
        "AAA,2025-01-13,10.5,1000\n"
        "AAA,2025-01-14,11.0,2000\n"
        "AAA,2025-01-14,11.0,2000\n"  # bilerek tekrar
        "BBB,2025-01-13,20.0,500\n",
        encoding="utf-8",
    )
    return path


def test_load_csv_basic(tmp_path: Path) -> None:
    csv_path = _write_sample_csv(tmp_path)
    rows = load_csv(
        csv_path,
        required_columns=["symbol", "date", "close"],
        schema={"close": float, "volume": int},
        date_field="date",
        unique_by=["symbol", "date"],
    )
    # Tekrarlı satır elenmiş olmalı
    assert len(rows) == 3
    # Tarihe göre sıralı
    assert [r["date"].isoformat()[:10] for r in rows] == ["2025-01-13", "2025-01-13", "2025-01-14"]
    # Tip dönüşümleri
    row0 = rows[0]
    assert isinstance(row0["close"], float)
    assert isinstance(row0["volume"], int)


def test_registry_load(tmp_path: Path) -> None:
    _write_sample_csv(tmp_path)
    spec = DatasetSpec(
        path="eod/quotes.csv",  # relative
        required_columns=["symbol", "date", "close"],
        schema={"close": float, "volume": int},
        date_field="date",
        unique_by=["symbol", "date"],
    )
    register_dataset("quotes", spec)

    rows = load_registered_dataset("quotes", base_dir=tmp_path)
    assert len(rows) == 3
    assert {r["symbol"] for r in rows} == {"AAA", "BBB"}


def test_missing_column_raises(tmp_path: Path) -> None:
    csv_path = _write_sample_csv(tmp_path)
    # "close" kolonunu zorunlu isteyip hatayı deniyoruz
    try:
        load_csv(csv_path, required_columns=["symbol", "date", "close", "nonexistent"])
    except ValueError as e:
        assert "missing required columns" in str(e)
    else:
        raise AssertionError("ValueError bekleniyordu")
